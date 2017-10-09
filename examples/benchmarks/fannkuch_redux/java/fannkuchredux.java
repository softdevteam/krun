/* The Computer Language Benchmarks Game
   http://shootout.alioth.debian.org/

   contributed by Isaac Gouy
   converted to Java by Oleg Mazurov
*/

public class fannkuchredux
{
    static void init() {};
    private static int EXPECT_CKSUM = 1616;
    private static int MAX_N = 8;


    public static int inner_iter() {
        int n = MAX_N;
        int[] perm = new int[n];
        int[] perm1 = new int[n];
        int[] count = new int[n];
        int maxFlipsCount = 0;
        int permCount = 0;
        int checksum = 0;

        for(int i=0; i<n; i++) perm1[i] = i;
        int r = n;

        while (true) {

            while (r != 1){ count[r-1] = r; r--; }

            for(int i=0; i<n; i++) perm[i] = perm1[i];
            int flipsCount = 0;
            int k;

            while ( !((k=perm[0]) == 0) ) {
                int k2 = (k+1) >> 1;
                for(int i=0; i<k2; i++) {
                    int temp = perm[i]; perm[i] = perm[k-i]; perm[k-i] = temp;
                }
                flipsCount++;
            }

            maxFlipsCount = Math.max(maxFlipsCount, flipsCount);
            checksum += permCount%2 == 0 ? flipsCount : -flipsCount;

            // Use incremental change to generate another permutation
            while (true) {
                if (r == n) {
                    if (checksum != EXPECT_CKSUM) {
                        System.out.println("bad checksum: " + checksum + " vs " + EXPECT_CKSUM);
                        System.exit(1);
                    }
                    return maxFlipsCount;
                }
                int perm0 = perm1[0];
                int i = 0;
                while (i < r) {
                    int j = i + 1;
                    perm1[i] = perm1[j];
                    i = j;
                }
                perm1[r] = perm0;

                count[r] = count[r] - 1;
                if (count[r] > 0) break;
                r++;
            }

            permCount++;
        }
    }

    public static void runIter(int n) {
        for (int i = 0; i < n; i++) {
            /* inner_iter() deals with state setup */
            inner_iter();
        }
    }
}
