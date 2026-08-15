int factorial(int a)
{
    int res = 1;
    for (int i = 1; i <= a; i++)
        res *= i;

    return res;
}

int main(void)
{
    return factorial(10);
}
