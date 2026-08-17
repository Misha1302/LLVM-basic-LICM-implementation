#include <stdio.h>
#include <stdlib.h>

int foo(int a, int b)
{
    int res = 1;
    for (int i = 1; i <= a && i > 0; )
    {
        if (a <= 5) {
            int c = a >= 5 ? abs(a - b) : a + b;
            i += c;
            res *= i;
        }
        else
        {
            int c = a * 2 - b;
            i += c;
            res *= i;
        }
    }

    return res;
}


int main(void)
{
    printf("%d\n", foo(50, 7));
    printf("%d\n", foo(2, 2));
    printf("%d\n", foo(3, 1));
    printf("%d\n", foo(40, -10));
    printf("%d\n", foo(-30, 7));

    return 0;
}