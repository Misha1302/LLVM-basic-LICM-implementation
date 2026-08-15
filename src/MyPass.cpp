#include "llvm/IR/Function.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Plugins/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"

using i64 = int64_t;

using namespace llvm;

namespace {
    enum class DfsColor {
        White,
        Gray,
        Black
    };

    class RPO_Printer {
        DenseMap<const BasicBlock *, DfsColor> BB_to_color;
        DenseMap<const BasicBlock *, i64> BB_to_id;
        SmallVector<std::pair<const BasicBlock *, const BasicBlock *> > back_edges;
        SmallVector<const BasicBlock *> postorder_BB;

        void initialize(const Function &function) {
            i64 id = 0;
            for (auto &BB: function) {
                BB_to_color[&BB] = DfsColor::White;
                BB_to_id[&BB] = id++;
            }
        }

        void dfs(const BasicBlock *u) {
            BB_to_color[u] = DfsColor::Gray;

            for (auto v: successors(u)) {
                if (BB_to_color[v] == DfsColor::Gray) {
                    back_edges.push_back({u, v});
                    continue;
                }

                if (BB_to_color[v] == DfsColor::White) {
                    dfs(v);
                }
            }

            postorder_BB.push_back(u);
            BB_to_color[u] = DfsColor::Black;
        }

        void print_info() {
            outs() << "RPO: \n";
            outs() << "[";
            for (i64 i = static_cast<i64>(postorder_BB.size()) - 1; i >= 0; i--) {
                if (i != 0)
                    outs() << BB_to_id[postorder_BB[i]] << ' ';
                else outs() << BB_to_id[postorder_BB[i]];
            }
            outs() << "]\n";

            outs() << "Back edges: \n";
            outs() << "[";
            for (i64 i = 0; i < back_edges.size(); i++) {
                auto [u, v] = back_edges[i];
                if (i != back_edges.size() - 1)
                    outs() << BB_to_id[u] << "->" << BB_to_id[v] << ", ";
                else outs() << BB_to_id[u] << "->" << BB_to_id[v];
            }
            outs() << "]\n";
        }

    public:
        void print_rpo(const Function &function) {
            initialize(function);
            if (!function.empty()) {
                dfs(&function.getEntryBlock());
            }
            print_info();
        }
    };

    class Instructions_Printer {
    private:
        DenseMap<unsigned, i64> get_instructions_info(const Function &function) {
            DenseMap<unsigned, i64> instr_to_count;
            for (auto &BB: function) {
                for (auto &instr: BB) {
                    instr_to_count[instr.getOpcode()]++;
                }
            }
            return instr_to_count;
        }

    public:
        void print_instructions_info(const Function &function) {
            auto info = get_instructions_info(function);
            outs() << "Instructions count:\n";
            for (auto [instr_opcode, count]: info) {
                outs() << "    " << Instruction::getOpcodeName(instr_opcode) << ": " << count << "\n";
            }
            outs() << "\n";
        }
    };

    struct MyPass : PassInfoMixin<MyPass> {
        static PreservedAnalyses run(const Function &function, FunctionAnalysisManager &) {
            outs() << "Function " << function.getName() << "\n\n";

            RPO_Printer rpo_printer;
            rpo_printer.print_rpo(function);

            outs() << "\n";

            Instructions_Printer instructions_printer;
            instructions_printer.print_instructions_info(function);


            for (i64 i = 0; i < 80; i++) {
                outs() << "-";
            }
            outs() << "\n";
            outs() << "\n";

            return PreservedAnalyses::all();
        }

        // Нужен для гарантированного запуска на IR,
        // который clang генерирует с -O0/optnone.
        static bool isRequired() {
            return true;
        }
    };
}

static void registerMyPass(PassBuilder &builder) {
    builder.registerPipelineParsingCallback(
        [](const StringRef name,
           FunctionPassManager &manager,
           ArrayRef<PassBuilder::PipelineElement>) {
            if (name != "MyPass") {
                return false;
            }

            manager.addPass(MyPass());
            return true;
        });
}

extern "C" LLVM_ATTRIBUTE_WEAK

PassPluginLibraryInfo llvmGetPassPluginInfo() {
    return {
        LLVM_PLUGIN_API_VERSION,
        "MyPass",
        LLVM_VERSION_STRING,
        registerMyPass
    };
}
