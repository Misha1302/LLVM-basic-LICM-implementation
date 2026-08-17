#include <stdio.h>

int foo(int a, int b)
{
    int res = 1;
    for (int i = 1; i <= a; )
    {
        int c = a - b;
        i += c;
        res *= i;
    }

    return res;
}


int main(void)
{
    printf("%d\n", foo(5, 7));
    printf("%d\n", foo(1, 2));
    printf("%d\n", foo(3, 0));
    printf("%d\n", foo(4, -10));
    printf("%d\n", foo(-3, 7));

    return 0;
}