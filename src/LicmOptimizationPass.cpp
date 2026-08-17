#include "llvm/IR/Function.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Plugins/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/Analysis/ValueTracking.h"

using i64 = int64_t;

using namespace llvm;

namespace {
    class LicmVerifier {
    public:
        bool can_be_moved_to_preheader(const Instruction &instruction, const Loop &loop) const {
            if (instruction.isTerminator()) return false;
            if (instruction.mayHaveSideEffects()) return false;
            if (instruction.mayReadOrWriteMemory()) return false;
            if (isa<PHINode>(&instruction)) return false;
            if (loop.getLoopPreheader() == nullptr) return false;
            if (!loop.hasLoopInvariantOperands(&instruction)) return false;
            if (!isSafeToSpeculativelyExecute(
                    &instruction,
                    nullptr, nullptr,
                    nullptr, nullptr,
                    true, false)
            )
                return false;

            return true;
        }
    };

    class LicmMover {
    public:
        void move_instruction_to_preheader(Loop &loop, Instruction &instruction) const {
            auto &preheader = *loop.getLoopPreheader();
            auto insert_it = preheader.getTerminator()->getIterator();
            instruction.moveBefore(preheader, insert_it);
        }
    };

    struct LicmOptimizationPass : PassInfoMixin<LicmOptimizationPass> {
        static void optimize_loop(
            const LoopInfo &loop_info,
            Loop &loop,
            const LicmVerifier &verifier,
            const LicmMover &mover
        ) {
            for (const auto inner_loop: loop.getSubLoops()) {
                optimize_loop(loop_info, *inner_loop, verifier, mover);
            }

            for (const auto bb: loop.getBlocks()) {
                if (loop_info.getLoopFor(bb) != &loop) {
                    continue;
                }

                for (auto it = bb->begin(); it != bb->end();) {
                    if (Instruction &instruction = *it++; verifier.can_be_moved_to_preheader(instruction, loop)) {
                        mover.move_instruction_to_preheader(loop, instruction);
                    }
                }
            }
        }

        static PreservedAnalyses run(Function &function, FunctionAnalysisManager &fam) {
            const auto &loopInfo = fam.getResult<LoopAnalysis>(function);

            for (const auto loop: loopInfo) {
                constexpr LicmVerifier verifier;
                constexpr LicmMover mover;
                optimize_loop(loopInfo, *loop, verifier, mover);
            }

            return PreservedAnalyses::none();
        }

        static bool isRequired() {
            return true;
        }
    };
}

static void registerLicmOptimizationPass(PassBuilder &builder) {
    builder.registerPipelineParsingCallback(
        [](const StringRef name,
           FunctionPassManager &manager,
           ArrayRef<PassBuilder::PipelineElement>) {
            if (name != "LicmOptimizationPass") {
                return false;
            }

            manager.addPass(LicmOptimizationPass());
            return true;
        });
}

extern "C" LLVM_ATTRIBUTE_WEAK

PassPluginLibraryInfo llvmGetPassPluginInfo() {
    return {
        LLVM_PLUGIN_API_VERSION,
        "LicmOptimizationPass",
        LLVM_VERSION_STRING,
        registerLicmOptimizationPass
    };
}
