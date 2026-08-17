; ModuleID = '/home/micodiy/razakov/cpp/MCST/LLVM-basic-LICM-implementation/tests/input.ll'
source_filename = "/home/micodiy/razakov/cpp/MCST/LLVM-basic-LICM-implementation/tests/input.c"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

; Function Attrs: noinline nounwind uwtable
define dso_local i32 @foo(i32 noundef %0, i32 noundef %1) #0 {
  %3 = sub nsw i32 %0, %1
  br label %4

4:                                                ; preds = %6, %2
  %.01 = phi i32 [ 1, %2 ], [ %8, %6 ]
  %.0 = phi i32 [ 1, %2 ], [ %7, %6 ]
  %5 = icmp sle i32 %.0, %0
  br i1 %5, label %6, label %9

6:                                                ; preds = %4
  %7 = add nsw i32 %.0, %3
  %8 = mul nsw i32 %.01, %7
  br label %4, !llvm.loop !6

9:                                                ; preds = %4
  ret i32 %.01
}

attributes #0 = { noinline nounwind uwtable "frame-pointer"="all" "min-legal-vector-width"="0" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }

!llvm.module.flags = !{!0, !1, !2, !3, !4}
!llvm.ident = !{!5}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 8, !"PIC Level", i32 2}
!2 = !{i32 7, !"PIE Level", i32 2}
!3 = !{i32 7, !"uwtable", i32 2}
!4 = !{i32 7, !"frame-pointer", i32 2}
!5 = !{!"clang version 22.1.8 (https://github.com/llvm/llvm-project ca7933e47d3a3451d81e72ac174dcb5aa28b59d1)"}
!6 = distinct !{!6, !7}
!7 = !{!"llvm.loop.mustprogress"}
