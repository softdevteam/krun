/*
 * The Computer Language Benchmarks Game
 * http://shootout.alioth.debian.org/
 *
 * contributed by Ledrug Katz
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <err.h>

#define MAX_N 8
#define EXPECT_CKSUM 1616

/* this depends highly on the platform.  It might be faster to use
   char type on 32-bit systems; it might be faster to use unsigned. */

typedef int elem;

elem s[MAX_N], t[MAX_N];

int maxflips = 0;
int odd = 0;
u_int32_t checksum = 0;


int flip()
{
   register int i;
   register elem *x, *y, c;

   for (x = t, y = s, i = MAX_N; i--; )
      *x++ = *y++;
   i = 1;
   do {
      for (x = t, y = t + t[0]; x < y; )
         c = *x, *x++ = *y, *y-- = c;
      i++;
   } while (t[t[0]]);
   return i;
}

void rotate(int n)
{
   elem c;
   register int i;
   c = s[0];
   for (i = 1; i <= n; i++) s[i-1] = s[i];
   s[n] = c;
}

/* Tompkin-Paige iterative perm generation */
void tk()
{
   int i = 0, f, n = MAX_N;
   elem c[MAX_N] = {0};

   while (i < n) {
      rotate(i);
      if (c[i] >= i) {
         c[i++] = 0;
         continue;
      }

      c[i]++;
      i = 1;
      odd = ~odd;
      if (*s) {
         f = s[s[0]] ? flip() : 1;
         if (f > maxflips) maxflips = f;
         checksum += odd ? -f : f;
      }
   }

   if (checksum != EXPECT_CKSUM) {
        errx(EXIT_FAILURE, "bad checksum: %d vs %d", checksum, EXPECT_CKSUM);
   }
}

void setup_state(void) {
   int i;

   for (i = 0; i < MAX_N; i++) {
      s[i] = i;
   }
   checksum = 0;
   maxflips = 0;
   odd = 0;
}

void run_iter(int n)
{
   int i;

   for (i = 0; i < n; i++) {
      setup_state();
      tk();
   }
}
