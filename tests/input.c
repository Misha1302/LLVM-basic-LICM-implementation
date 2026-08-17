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