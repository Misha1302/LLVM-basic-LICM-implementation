#include "llvm/IR/Function.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Plugins/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

namespace {

struct MyPass : PassInfoMixin<MyPass> {
    PreservedAnalyses run(Function& function,
                          FunctionAnalysisManager&) {
        outs() << "Function "
               << function.getName()
               << "(): "
               << function.arg_size()
               << " arguments\n";

        return PreservedAnalyses::all();
    }

    // Нужен для гарантированного запуска на IR,
    // который clang генерирует с -O0/optnone.
    static bool isRequired() {
        return true;
    }
};

} // namespace

static void registerMyPass(PassBuilder& builder) {
    builder.registerPipelineParsingCallback(
        [](StringRef name,
           FunctionPassManager& manager,
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
