package com.evie.eyes.core

import java.math.BigInteger
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Gerador idêntico ao `random.Random` do Python (Mersenne Twister MT19937).
 *
 * Com a mesma seed, [random], [uniform], [gauss], [choice] e [randrange] devolvem exatamente os
 * mesmos valores do Python 3, então a animação gerada pela mesma seed é a mesma nas duas versões.
 */
class PyRandom(seed: Long? = null) {
    private val mt = IntArray(N)
    private var index = N
    private var gaussNext: Double? = null

    init {
        reseed(seed ?: java.util.concurrent.ThreadLocalRandom.current().nextLong())
    }

    /** Equivale a `random.seed(int)`: usa |seed| em palavras de 32 bits (little-endian). */
    fun reseed(seed: Long) {
        var n = BigInteger.valueOf(seed).abs()
        val mask = BigInteger.valueOf(0xFFFFFFFFL)
        val key = ArrayList<Int>()
        while (n.signum() > 0) {
            key.add(n.and(mask).toLong().toInt())
            n = n.shiftRight(32)
        }
        if (key.isEmpty()) key.add(0)
        initByArray(key.toIntArray())
        gaussNext = null
    }

    private fun initGenrand(s: Int) {
        mt[0] = s
        for (i in 1 until N) {
            val prev = mt[i - 1]
            mt[i] = 1812433253 * (prev xor (prev ushr 30)) + i
        }
        index = N
    }

    private fun initByArray(key: IntArray) {
        initGenrand(19650218)
        var i = 1
        var j = 0
        var k = maxOf(N, key.size)
        while (k > 0) {
            val prev = mt[i - 1]
            mt[i] = (mt[i] xor ((prev xor (prev ushr 30)) * 1664525)) + key[j] + j
            i++
            j++
            if (i >= N) {
                mt[0] = mt[N - 1]
                i = 1
            }
            if (j >= key.size) j = 0
            k--
        }
        k = N - 1
        while (k > 0) {
            val prev = mt[i - 1]
            mt[i] = (mt[i] xor ((prev xor (prev ushr 30)) * 1566083941)) - i
            i++
            if (i >= N) {
                mt[0] = mt[N - 1]
                i = 1
            }
            k--
        }
        mt[0] = Int.MIN_VALUE
        index = N
    }

    private fun twist() {
        val mag = intArrayOf(0, MATRIX_A)
        var kk = 0
        while (kk < N - M) {
            val y = (mt[kk] and UPPER_MASK) or (mt[kk + 1] and LOWER_MASK)
            mt[kk] = mt[kk + M] xor (y ushr 1) xor mag[y and 1]
            kk++
        }
        while (kk < N - 1) {
            val y = (mt[kk] and UPPER_MASK) or (mt[kk + 1] and LOWER_MASK)
            mt[kk] = mt[kk + (M - N)] xor (y ushr 1) xor mag[y and 1]
            kk++
        }
        val y = (mt[N - 1] and UPPER_MASK) or (mt[0] and LOWER_MASK)
        mt[N - 1] = mt[M - 1] xor (y ushr 1) xor mag[y and 1]
        index = 0
    }

    /** Próxima palavra de 32 bits (tratada como sem sinal pelos chamadores). */
    private fun nextInt32(): Int {
        if (index >= N) twist()
        var y = mt[index++]
        y = y xor (y ushr 11)
        y = y xor ((y shl 7) and TEMPER_B)
        y = y xor ((y shl 15) and TEMPER_C)
        y = y xor (y ushr 18)
        return y
    }

    /** `random.random()`: float em [0, 1) com 53 bits. */
    fun random(): Double {
        val a = nextInt32() ushr 5
        val b = nextInt32() ushr 6
        return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0)
    }

    /** `random.uniform(a, b)`. */
    fun uniform(a: Double, b: Double): Double = a + (b - a) * random()

    /** `random.gauss(mu, sigma)` (par de Box-Muller com cache, como no Python 3.10). */
    fun gauss(mu: Double, sigma: Double): Double {
        var z = gaussNext
        gaussNext = null
        if (z == null) {
            val x2pi = random() * TWO_PI
            val g2rad = sqrt(-2.0 * ln(1.0 - random()))
            z = cos(x2pi) * g2rad
            gaussNext = sin(x2pi) * g2rad
        }
        return mu + z * sigma
    }

    /** `random.getrandbits(k)` para 1 <= k <= 32. */
    fun getRandBits(k: Int): Long {
        require(k in 1..32) { "k fora de 1..32: $k" }
        return (nextInt32().toLong() and 0xFFFFFFFFL) ushr (32 - k)
    }

    private fun randBelow(n: Long): Long {
        require(n > 0) { "n precisa ser positivo" }
        val k = 64 - java.lang.Long.numberOfLeadingZeros(n)
        var r = getRandBits(k)
        while (r >= n) r = getRandBits(k)
        return r
    }

    /** `random.randrange(n)` = inteiro em [0, n). */
    fun randRange(n: Int): Int = randBelow(n.toLong()).toInt()

    /** `random.choice(seq)`. */
    fun <T> choice(items: List<T>): T = items[randBelow(items.size.toLong()).toInt()]

    private companion object {
        const val N = 624
        const val M = 397
        const val UPPER_MASK = Int.MIN_VALUE
        const val LOWER_MASK = 0x7fffffff
        const val MATRIX_A = 0x9908b0df.toInt()
        const val TEMPER_B = 0x9d2c5680.toInt()
        const val TEMPER_C = 0xefc60000.toInt()
        const val TWO_PI = 2.0 * PI
    }
}
