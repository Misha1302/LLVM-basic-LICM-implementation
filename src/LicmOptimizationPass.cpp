#include "llvm/IR/Function.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Plugins/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Analysis/LoopInfo.h"

using i64 = int64_t;

using namespace llvm;

namespace {
    struct LicmOptimizationPass : PassInfoMixin<LicmOptimizationPass> {
        static PreservedAnalyses run(Function &function, FunctionAnalysisManager &fam) {
            LoopInfo &loopInfo = fam.getResult<LoopAnalysis>(function);

            for (Loop *loop : loopInfo) {
                if (BasicBlock *header = loop->getHeader()) {
                    errs() << "Loop header: "
                           << header->getName()
                           << '\n';
                }
            }

            return PreservedAnalyses::all();
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
