/*
 * Host-side test for native/fp_single.c: compares __mulsf3/__divsf3 against
 * the host's hardware IEEE single precision (round-to-nearest-even) bit for
 * bit. Build and run on the PC, never on the Amiga:
 *
 *   gcc -O2 -I native -o /tmp/tfp build/test_fp_single.c && /tmp/tfp
 *
 * fp_single.c is included with its functions renamed so they do not collide
 * with the host libgcc's own soft-float entry points.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

#define __mulsf3 amiga_mulsf3
#define __divsf3 amiga_divsf3
#include "../native/fp_single.c"
#undef __mulsf3
#undef __divsf3

static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float    flt(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static int is_nan(uint32_t u) { return (u & 0x7f800000u) == 0x7f800000u && (u & 0x7fffffu); }

static uint64_t rng = 0x9E3779B97F4A7C15ull;
static uint32_t rnd(void)
{
	rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
	return (uint32_t)(rng >> 11);
}

/* A random float biased toward interesting shapes: any bit pattern, plus
 * frequent subnormals, near-overflow, powers of two and small integers. */
static uint32_t rnd_float(void)
{
	uint32_t r = rnd();
	switch (rnd() % 8) {
	case 0: return r & 0x807fffffu;                                   /* subnormal / zero   */
	case 1: return (r & 0x80ffffffu) | 0x7e000000u;                   /* huge exponent      */
	case 2: return (r & 0x80000000u) | ((rnd() % 254 + 1) << 23);     /* power of two       */
	case 3: { union { float f; uint32_t u; } c; c.f = (float)(int)(rnd() % 2000) - 1000.0f; return c.u; }
	case 4: return (r & 0x80ffffffu) | 0x00800000u;                   /* tiny normal        */
	default: return r;
	}
}

static long fails = 0, tests = 0;

static void check(const char *op, uint32_t a, uint32_t b, uint32_t got, uint32_t want)
{
	tests++;
	if (got == want) return;
	if (is_nan(got) && is_nan(want)) return;   /* NaN payload/sign is unspecified */
	if (fails < 25)
		printf("FAIL %s  a=%08x b=%08x  got=%08x want=%08x  (%.9g %s %.9g)\n",
		       op, a, b, got, want, flt(a), op, flt(b));
	fails++;
}

static void one(uint32_t a, uint32_t b)
{
	volatile float fa = flt(a), fb = flt(b);
	float hm = fa * fb;                /* host hardware, single precision */
	float hd = fa / fb;
	check("*", a, b, bits(amiga_mulsf3(fa, fb)), bits(hm));
	check("/", a, b, bits(amiga_divsf3(fa, fb)), bits(hd));
}

int main(void)
{
	static const uint32_t edge[] = {
		0x00000000, 0x80000000, 0x3f800000, 0xbf800000, 0x40000000, 0x40400000,
		0x447a0000, 0x42700000, 0x00000001, 0x80000001, 0x007fffff, 0x00800000,
		0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001,
		0x3effffff, 0x3f000000, 0x3f7fffff, 0x4b800000, 0x4f000000, 0x33800000,
		0x0d800000, 0x00400000, 0x00000002, 0x7effffff, 0x01000000, 0x3fb504f3,
	};
	size_t n = sizeof(edge) / sizeof(edge[0]), i, j;
	long k;

	/* every pair of edge values, both orders */
	for (i = 0; i < n; i++)
		for (j = 0; j < n; j++)
			one(edge[i], edge[j]);
	/* edge against random */
	for (i = 0; i < n; i++)
		for (k = 0; k < 20000; k++) {
			one(edge[i], rnd_float());
			one(rnd_float(), edge[i]);
		}
	/* random against random */
	for (k = 0; k < 4000000; k++)
		one(rnd_float(), rnd_float());

	printf("%ld comparisons, %ld failures\n", tests, fails);
	return fails ? 1 : 0;
}
