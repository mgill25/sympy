from core import C
from sympify import converter, sympify, _sympify, SympifyError
from basic import Basic
from singleton import S, Singleton
from expr import Expr, AtomicExpr
from decorators import _sympifyit, deprecated, call_highest_priority
from cache import cacheit, clear_cache
from sympy.core.compatibility import as_int, HAS_GMPY, SYMPY_INTS
import sympy.mpmath as mpmath
import sympy.mpmath.libmp as mlib
from sympy.mpmath.libmp import mpf_pow, mpf_pi, mpf_e, phi_fixed
from sympy.mpmath.ctx_mp import mpnumeric
from sympy.mpmath.libmp.libmpf import (
    finf as _mpf_inf, fninf as _mpf_ninf,
    fnan as _mpf_nan, fzero as _mpf_zero, _normalize as mpf_normalize)

import decimal
import math
import re as regex
from collections import defaultdict

rnd = mlib.round_nearest

_LOG2 = math.log(2)


def mpf_norm(mpf, prec):
    """Return the mpf tuple normalized appropriately for the indicated
    precision.

    This also contains a portion of code to not return zero if
    the mantissa is 0; this is a necessary (but not sufficient) test of
    zero since the mantissa for mpf's values "+inf", "-inf" and "nan" have
    a mantissa of zero, too.
    """
    sign, man, expt, bc = mpf
    if not man:
        # hack for mpf_normalize which does not do this;
        # it assumes that if man is zero the result is 0
        # (see issue 3540)
        if not bc:
            return _mpf_zero
        else:
            # don't change anything; this should already
            # be a well formed mpf tuple
            return mpf
    rv = mpf_normalize(sign, man, expt, bc, prec, rnd)
    return rv

# TODO: we should use the warnings module
_errdict = {"divide": False}


def seterr(divide=False):
    """
    Should sympy raise an exception on 0/0 or return a nan?

    divide == True .... raise an exception
    divide == False ... return nan
    """
    if _errdict["divide"] != divide:
        clear_cache()
        _errdict["divide"] = divide


def _as_integer_ratio(p):
    """compatibility implementation for python < 2.6"""
    neg_pow, man, expt, bc = getattr(p, '_mpf_', mpmath.mpf(p)._mpf_)
    p = [1, -1][neg_pow % 2]*man
    if expt < 0:
        q = 2**-expt
    else:
        q = 1
        p *= 2**expt
    return int(p), int(q)


def _decimal_to_Rational_prec(dec):
    """Convert an ordinary decimal instance to a Rational."""
    # _is_special is needed for Python 2.5 support; is_finite for Python 3.3
    # support
    nonfinite = getattr(dec, '_is_special', None)
    if nonfinite is None:
        nonfinite = not dec.is_finite()
    if nonfinite:
        raise TypeError("dec must be finite, got %s." % dec)
    s, d, e = dec.as_tuple()
    prec = len(d)
    if e >= 0:  # it's an integer
        rv = Integer(int(dec))
    else:
        s = (-1)**s
        d = sum([di*10**i for i, di in enumerate(reversed(d))])
        rv = Rational(s*d, 10**-e)
    return rv, prec


def _literal_float(f):
    """Return True if n can be interpreted as a floating point number."""
    pat = r"[-+]?((\d*\.\d+)|(\d+\.?))(eE[-+]?\d+)?"
    return bool(regex.match(pat, f))

# (a,b) -> gcd(a,b)
_gcdcache = {}

# TODO caching with decorator, but not to degrade performance


def igcd(a, b):
    """Computes positive, integer greatest common divisor of two numbers.

       The algorithm is based on the well known Euclid's algorithm. To
       improve speed, igcd() has its own caching mechanism implemented.
    """
    try:
        return _gcdcache[(a, b)]
    except KeyError:
        a, b = as_int(a), as_int(b)

        if a and b:
            if b < 0:
                b = -b

            while b:
                a, b = b, a % b
        else:
            a = abs(a or b)

        _gcdcache[(a, b)] = a
        return a


def ilcm(a, b):
    """Computes integer least common multiple of two numbers. """
    if a == 0 and b == 0:
        return 0
    else:
        return a*b // igcd(a, b)


def igcdex(a, b):
    """Returns x, y, g such that g = x*a + y*b = gcd(a, b).

       >>> from sympy.core.numbers import igcdex
       >>> igcdex(2, 3)
       (-1, 1, 1)
       >>> igcdex(10, 12)
       (-1, 1, 2)

       >>> x, y, g = igcdex(100, 2004)
       >>> x, y, g
       (-20, 1, 4)
       >>> x*100 + y*2004
       4

    """
    if (not a) and (not b):
        return (0, 1, 0)

    if not a:
        return (0, b//abs(b), abs(b))
    if not b:
        return (a//abs(a), 0, abs(a))

    if a < 0:
        a, x_sign = -a, -1
    else:
        x_sign = 1

    if b < 0:
        b, y_sign = -b, -1
    else:
        y_sign = 1

    x, y, r, s = 1, 0, 0, 1

    while b:
        (c, q) = (a % b, a // b)
        (a, b, r, s, x, y) = (b, c, x - q*r, y - q*s, r, s)

    return (x*x_sign, y*y_sign, a)


class Number(AtomicExpr):
    """
    Represents any kind of number in sympy.

    Floating point numbers are represented by the Float class.
    Integer numbers (of any size), together with rational numbers (again,
    there is no limit on their size) are represented by the Rational class.

    If you want to represent, for example, ``1+sqrt(2)``, then you need to do::

      Rational(1) + sqrt(Rational(2))
    """
    is_commutative = True
    is_number = True

    __slots__ = []

    # Used to make max(x._prec, y._prec) return x._prec when only x is a float
    _prec = -1

    is_Number = True

    def __new__(cls, *obj):
        if len(obj) == 1:
            obj = obj[0]

        if isinstance(obj, Number):
            return obj
        if isinstance(obj, (int, long)):
            return Integer(obj)
        if isinstance(obj, tuple) and len(obj) == 2:
            return Rational(*obj)
        if isinstance(obj, (float, mpmath.mpf, decimal.Decimal)):
            return Float(obj)
        if isinstance(obj, basestring):
            val = sympify(obj)
            if isinstance(val, Number):
                return val
            else:
                raise ValueError('String "%s" does not denote a Number' % obj)
            if isinstance(obj, Number):
                return obj
        msg = "expected str|int|long|float|Decimal|Number object but got %r"
        raise TypeError(msg % type(obj).__name__)

    def __divmod__(self, other):
        from containers import Tuple
        from sympy.functions.elementary.complexes import sign

        try:
            other = Number(other)
        except TypeError:
            msg = "unsupported operand type(s) for divmod(): '%s' and '%s'"
            raise TypeError(msg % (type(self).__name__, type(other).__name__))
        if not other:
            raise ZeroDivisionError('modulo by zero')
        if self.is_Integer and other.is_Integer:
            return Tuple(*divmod(self.p, other.p))
        else:
            rat = self/other
        w = sign(rat)*int(abs(rat))  # = rat.floor()
        r = self - other*w
        #w*other + r == self
        return Tuple(w, r)

    def __rdivmod__(self, other):
        try:
            other = Number(other)
        except TypeError:
            msg = "unsupported operand type(s) for divmod(): '%s' and '%s'"
            raise TypeError(msg % (type(other).__name__, type(self).__name__))
        return divmod(other, self)

    def __round__(self, *args):
        return round(float(self), *args)

    def _as_mpf_val(self, prec):
        """Evaluation of mpf tuple accurate to at least prec bits."""
        raise NotImplementedError('%s needs ._as_mpf_val() method' %
            (self.__class__.__name__))

    def _eval_evalf(self, prec):
        return Float._new(self._as_mpf_val(prec), prec)

    def _as_mpf_op(self, prec):
        prec = max(prec, self._prec)
        return self._as_mpf_val(prec), prec

    def __float__(self):
        return mlib.to_float(self._as_mpf_val(53))

    def _eval_conjugate(self):
        return self

    def _eval_order(self, *symbols):
        # Order(5, x, y) -> Order(1,x,y)
        return C.Order(S.One, *symbols)

    def _eval_subs(self, old, new):
        if old == -self:
            return -new
        return self  # there is no other possibility

    def _eval_is_bounded(self):
        return True

    def _eval_is_finite(self):
        return True

    @classmethod
    def class_key(cls):
        return 1, 0, 'Number'

    @cacheit
    def sort_key(self, order=None):
        return self.class_key(), (0, ()), (), self

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        if isinstance(other, Number):
            if other is S.NaN:
                return S.NaN
            elif other is S.Infinity:
                return S.Infinity
            elif other is S.NegativeInfinity:
                return S.NegativeInfinity
        return AtomicExpr.__add__(self, other)

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        if isinstance(other, Number):
            if other is S.NaN:
                return S.NaN
            elif other is S.Infinity:
                return S.NegativeInfinity
            elif other is S.NegativeInfinity:
                return S.Infinity
        return AtomicExpr.__sub__(self, other)

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        if isinstance(other, Number):
            if other is S.NaN:
                return S.NaN
            elif other is S.Infinity:
                if self.is_zero:
                    return S.NaN
                elif self.is_positive:
                    return S.Infinity
                else:
                    return S.NegativeInfinity
            elif other is S.NegativeInfinity:
                if self.is_zero:
                    return S.NaN
                elif self.is_positive:
                    return S.NegativeInfinity
                else:
                    return S.Infinity
        return AtomicExpr.__mul__(self, other)

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        if isinstance(other, Number):
            if other is S.NaN:
                return S.NaN
            elif other is S.Infinity or other is S.NegativeInfinity:
                return S.Zero
        return AtomicExpr.__div__(self, other)

    __truediv__ = __div__

    def __eq__(self, other):
        raise NotImplementedError('%s needs .__eq__() method' %
            (self.__class__.__name__))

    def __ne__(self, other):
        raise NotImplementedError('%s needs .__ne__() method' %
            (self.__class__.__name__))

    def __lt__(self, other):
        raise NotImplementedError('%s needs .__lt__() method' %
            (self.__class__.__name__))

    def __le__(self, other):
        raise NotImplementedError('%s needs .__le__() method' %
            (self.__class__.__name__))

    def __gt__(self, other):
        return _sympify(other).__lt__(self)

    def __ge__(self, other):
        return _sympify(other).__le__(self)

    def __hash__(self):
        return super(Number, self).__hash__()

    def is_constant(self, *wrt, **flags):
        return True

    def as_coeff_mul(self, *deps):
        # a -> c*t
        if self.is_Rational:
            return self, tuple()
        elif self.is_negative:
            return S.NegativeOne, (-self,)
        return S.One, (self,)

    def as_coeff_add(self, *deps):
        # a -> c + t
        if self.is_Rational:
            return self, tuple()
        return S.Zero, (self,)

    def as_coeff_Mul(self, rational=False):
        """Efficiently extract the coefficient of a product. """
        if rational and not self.is_Rational:
            return S.One, self
        return self, S.One

    def as_coeff_Add(self):
        """Efficiently extract the coefficient of a summation. """
        return self, S.Zero

    def gcd(self, other):
        """Compute GCD of `self` and `other`. """
        from sympy.polys import gcd
        return gcd(self, other)

    def lcm(self, other):
        """Compute LCM of `self` and `other`. """
        from sympy.polys import lcm
        return lcm(self, other)

    def cofactors(self, other):
        """Compute GCD and cofactors of `self` and `other`. """
        from sympy.polys import cofactors
        return cofactors(self, other)


class Float(Number):
    """
    Represents a floating point number. It is capable of representing
    arbitrary-precision floating-point numbers.

    Examples
    ========

    >>> from sympy import Float, pi
    >>> Float(3.5)
    3.50000000000000
    >>> Float(3)
    3.00000000000000

    Floats can be created from a string representations of Python floats
    to force ints to Float or to enter high-precision (> 15 significant
    digits) values:

    >>> Float('.0010')
    0.00100000000000000
    >>> Float('1e-3')
    0.00100000000000000
    >>> Float('1e-3', 3)
    0.00100

    Float can automatically count significant figures if a null string
    is sent for the precision; space are also allowed in the string. (Auto-
    counting is only allowed for strings, ints and longs).

    >>> Float('123 456 789 . 123 456', '')
    123456789.123456
    >>> Float('12e-3', '')
    0.012
    >>> Float(3, '')
    3.

    If a number is written in scientific notation, only the digits before the
    exponent are considered significant if a decimal appears, otherwise the
    "e" signifies only how to move the decimal:

    >>> Float('60.e2', '')  # 2 digits significant
    6.0e+3
    >>> Float('60e2', '')  # 4 digits significant
    6000.
    >>> Float('600e-2', '')  # 3 digits significant
    6.00

    Notes
    =====

    Floats are inexact by their nature unless their value is a binary-exact
    value.

    >>> approx, exact = Float(.1, 1), Float(.125, 1)

    For calculation purposes, evalf needs to be able to change the precision
    but this will not increase the accuracy of the inexact value. The
    following is the most accurate 5-digit approximation of a value of 0.1
    that had only 1 digit of precision:

    >>> approx.evalf(5)
    0.099609

    By contrast, 0.125 is exact in binary (as it is in base 10) and so it
    can be passed to Float or evalf to obtain an arbitrary precision with
    matching accuracy:

    >>> Float(exact, 5)
    0.12500
    >>> exact.evalf(20)
    0.12500000000000000000

    Trying to make a high-precision Float from a float is not disallowed,
    but one must keep in mind that the *underlying float* (not the apparent
    decimal value) is being obtained with high precision. For example, 0.3
    does not have a finite binary representation. The closest rational is
    the fraction 5404319552844595/2**54. So if you try to obtain a Float of
    0.3 to 20 digits of precision you will not see the same thing as 0.3
    followed by 19 zeros:

    >>> Float(0.3, 20)
    0.29999999999999998890

    If you want a 20-digit value of the decimal 0.3 (not the floating point
    approximation of 0.3) you should send the 0.3 as a string. The underlying
    representation is still binary but a higher precision than Python's float
    is used:

    >>> Float('0.3', 20)
    0.30000000000000000000

    Although you can increase the precision of an existing Float using Float
    it will not increase the accuracy -- the underlying value is not changed:

    >>> def show(f): # binary rep of Float
    ...     from sympy import Mul, Pow
    ...     s, m, e, b = f._mpf_
    ...     v = Mul(int(m), Pow(2, int(e), evaluate=False), evaluate=False)
    ...     print '%s at prec=%s' % (v, f._prec)
    ...
    >>> t = Float('0.3', 3)
    >>> show(t)
    4915/2**14 at prec=13
    >>> show(Float(t, 20)) # higher prec, not higher accuracy
    4915/2**14 at prec=70
    >>> show(Float(t, 2)) # lower prec
    307/2**10 at prec=10

    The same thing happens when evalf is used on a Float:

    >>> show(t.evalf(20))
    4915/2**14 at prec=70
    >>> show(t.evalf(2))
    307/2**10 at prec=10

    Finally, Floats can be instantiated with an mpf tuple (n, c, p) to
    produce the number (-1)**n*c*2**p:

    >>> n, c, p = 1, 5, 0
    >>> (-1)**n*c*2**p
    -5
    >>> Float((1, 5, 0))
    -5.00000000000000

    An actual mpf tuple also contains the number of bits in c as the last
    element of the tuple, but this is not needed for instantiation:

    >>> _._mpf_
    (1, 5, 0, 3)

    That last value can be used to create the corresponding Float, however,
    by passing the tuple and prec='' to Float to copy the precision from the
    mpf tuple:

    >>> Float(pi.n(5)._mpf_, '')
    3.1416

    """
    __slots__ = ['_mpf_', '_prec']

    is_rational = True
    is_real = True

    is_Float = True

    def __new__(cls, num, prec=15):
        if isinstance(num, basestring):
            num = num.replace(' ', '')
            if num.startswith('.') and len(num) > 1:
                num = '0' + num
            elif num.startswith('-.') and len(num) > 2:
                num = '-0.' + num[2:]
        elif isinstance(num, float) and num == 0:
            num = '0'
        elif isinstance(num, (SYMPY_INTS, Integer)):
            num = str(num)  # faster than mlib.from_int
        elif isinstance(num, mpmath.mpf):
            num = num._mpf_

        if prec == '':
            if type(num) is tuple and len(num) == 4:
                return Float._new(num, num[-1])
            elif not isinstance(num, basestring):
                raise ValueError('The null string can only be used when '
                'the number to Float is passed as a string or is a tuple '
                'with length of 4.')
            ok = None
            if _literal_float(num):
                try:
                    Num = decimal.Decimal(num)
                except decimal.InvalidOperation:
                    pass
                else:
                    isint = '.' not in num
                    num, dps = _decimal_to_Rational_prec(Num)
                    if num.is_Integer and isint:
                        dps = max(dps, len(str(num).lstrip('-')))
                    ok = True
            if ok is None:
                raise ValueError('string-float not recognized: %s' % num)
        else:
            dps = prec

        prec = mlib.libmpf.dps_to_prec(dps)
        if isinstance(num, float):
            _mpf_ = mlib.from_float(num, prec, rnd)
        elif isinstance(num, str):
            _mpf_ = mlib.from_str(num, prec, rnd)
        elif isinstance(num, decimal.Decimal):
            _mpf_ = mlib.from_str(str(num), prec, rnd)
        elif isinstance(num, Rational):
            _mpf_ = mlib.from_rational(num.p, num.q, prec, rnd)
        elif isinstance(num, tuple) and len(num) in (3, 4):
            if type(num[1]) is str:
                # it's a hexadecimal (coming from a pickled object)
                # assume that it is in standard form
                num = list(num)
                num[1] = long(num[1], 16)
                _mpf_ = tuple(num)
            else:
                if not num[1] and len(num) == 4:
                    # handle normalization hack
                    return Float._new(num, prec)
                else:
                    _mpf_ = mpmath.mpf(
                        S.NegativeOne**num[0]*num[1]*2**num[2])._mpf_
        elif isinstance(num, Float):
            _mpf_ = num._mpf_
            if prec < num._prec:
                _mpf_ = mpf_norm(_mpf_, prec)
        else:
            _mpf_ = mpmath.mpf(num)._mpf_

        # special cases
        if _mpf_ == _mpf_zero:
            pass  # we want a Float
        elif _mpf_ == _mpf_nan:
            return S.NaN

        obj = Expr.__new__(cls)
        obj._mpf_ = _mpf_
        obj._prec = prec
        return obj

    @classmethod
    def _new(cls, _mpf_, _prec):
        # special cases
        if _mpf_ == _mpf_zero:
            return S.Zero  # XXX this is different from Float which gives 0.0
        elif _mpf_ == _mpf_nan:
            return S.NaN

        # the new Float should be normalized unless it is
        # an integer because Float doesn't return Floats
        # for Integers. If Integers can become Floats then
        # all the following (up to the first 'obj =' line
        # can be replaced with ok = mpf_norm(_mpf_, _prec)

        sign, man, expt, bc = _mpf_
        if not man:
            # hack for mpf_normalize which does not do this
            if not bc:
                ok = _mpf_zero
            else:
                ok = (sign % 2, long(man), expt, bc)
        elif expt < 0:
            # this is the non-hack normalization
            ok = mpf_normalize(sign, man, expt, bc, _prec, rnd)
        else:
            ok = _mpf_

        obj = Expr.__new__(cls)
        obj._mpf_ = ok
        obj._prec = _prec
        return obj

    # mpz can't be pickled
    def __getnewargs__(self):
        return (mlib.to_pickable(self._mpf_),)

    def __getstate__(self):
        return {'_prec': self._prec}

    def _hashable_content(self):
        return (self._mpf_, self._prec)

    def floor(self):
        return C.Integer(int(mlib.to_int(
            mlib.mpf_floor(self._mpf_, self._prec))))

    def ceiling(self):
        return C.Integer(int(mlib.to_int(
            mlib.mpf_ceil(self._mpf_, self._prec))))

    @property
    def num(self):
        return mpmath.mpf(self._mpf_)

    def _as_mpf_val(self, prec):
        rv = mpf_norm(self._mpf_, prec)
        # uncomment to see failures
        #if rv != was._mpf_ and self._prec == prec:
        #    print was._mpf_, rv
        return rv

    def _as_mpf_op(self, prec):
        return self._mpf_, max(prec, self._prec)

    def _eval_is_bounded(self):
        if self._mpf_ in (_mpf_inf, _mpf_ninf):
            return False
        return True

    def _eval_is_finite(self):
        if self._mpf_ in (_mpf_inf, _mpf_ninf, _mpf_zero):
            return False
        return True

    def _eval_is_integer(self):
        return self._mpf_ == _mpf_zero

    def _eval_is_negative(self):
        if self._mpf_ == _mpf_ninf:
            return True
        if self._mpf_ == _mpf_inf:
            return False
        return self.num < 0

    def _eval_is_positive(self):
        if self._mpf_ == _mpf_inf:
            return True
        if self._mpf_ == _mpf_ninf:
            return False
        return self.num > 0

    def _eval_is_zero(self):
        return self._mpf_ == _mpf_zero

    def __nonzero__(self):
        return self._mpf_ != _mpf_zero

    def __neg__(self):
        return Float._new(mlib.mpf_neg(self._mpf_), self._prec)

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        if isinstance(other, Number):
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_add(self._mpf_, rhs, prec, rnd), prec)
        return Number.__add__(self, other)

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        if isinstance(other, Number):
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_sub(self._mpf_, rhs, prec, rnd), prec)
        return Number.__sub__(self, other)

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        if isinstance(other, Number):
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_mul(self._mpf_, rhs, prec, rnd), prec)
        return Number.__mul__(self, other)

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        if isinstance(other, Number) and other != 0:
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_div(self._mpf_, rhs, prec, rnd), prec)
        return Number.__div__(self, other)

    __truediv__ = __div__

    @_sympifyit('other', NotImplemented)
    def __mod__(self, other):
        if isinstance(other, Number):
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_mod(self._mpf_, rhs, prec, rnd), prec)
        return Number.__mod__(self, other)

    @_sympifyit('other', NotImplemented)
    def __rmod__(self, other):
        if isinstance(other, Number):
            rhs, prec = other._as_mpf_op(self._prec)
            return Float._new(mlib.mpf_mod(rhs, self._mpf_, prec, rnd), prec)
        return Number.__rmod__(self, other)

    def _eval_power(self, expt):
        """
        expt is symbolic object but not equal to 0, 1

        (-p)**r -> exp(r*log(-p)) -> exp(r*(log(p) + I*Pi)) ->
                  -> p**r*(sin(Pi*r) + cos(Pi*r)*I)
        """
        if self == 0:
            if expt.is_positive:
                return S.Zero
            if expt.is_negative:
                return Float('inf')
        if isinstance(expt, Number):
            if isinstance(expt, Integer):
                prec = self._prec
                return Float._new(
                    mlib.mpf_pow_int(self._mpf_, expt.p, prec, rnd), prec)
            expt, prec = expt._as_mpf_op(self._prec)
            self = self._mpf_
            try:
                y = mpf_pow(self, expt, prec, rnd)
                return Float._new(y, prec)
            except mlib.ComplexResult:
                re, im = mlib.mpc_pow(
                    (self, _mpf_zero), (expt, _mpf_zero), prec, rnd)
                return Float._new(re, prec) + \
                    Float._new(im, prec)*S.ImaginaryUnit

    def __abs__(self):
        return Float._new(mlib.mpf_abs(self._mpf_), self._prec)

    def __int__(self):
        if self._mpf_ == _mpf_zero:
            return 0
        return int(mlib.to_int(self._mpf_))  # uses round_fast = round_down

    def __eq__(self, other):
        if isinstance(other, float):
            # coerce to Float at same precision
            o = Float(other)
            try:
                ompf = o._as_mpf_val(self._prec)
            except ValueError:
                return False
            return bool(mlib.mpf_eq(self._mpf_, ompf))
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy != other  -->  not ==
        if isinstance(other, NumberSymbol):
            if other.is_irrational:
                return False
            return other.__eq__(self)
        if isinstance(other, Float):
            return bool(mlib.mpf_eq(self._mpf_, other._mpf_))
        if isinstance(other, Number):
            # numbers should compare at the same precision;
            # all _as_mpf_val routines should be sure to abide
            # by the request to change the prec if necessary; if
            # they don't, the equality test will fail since it compares
            # the mpf tuples
            ompf = other._as_mpf_val(self._prec)
            return bool(mlib.mpf_eq(self._mpf_, ompf))
        return False    # Float != non-Number

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other
        if isinstance(other, NumberSymbol):
            return other.__le__(self)
        if other.is_comparable:
            other = other.evalf()
        if isinstance(other, Number):
            return bool(mlib.mpf_gt(self._mpf_, other._as_mpf_val(self._prec)))
        return Expr.__gt__(self, other)

    def __ge__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  -->  ! <=
        if isinstance(other, NumberSymbol):
            return other.__lt__(self)
        if other.is_comparable:
            other = other.evalf()
        if isinstance(other, Number):
            return bool(mlib.mpf_ge(self._mpf_, other._as_mpf_val(self._prec)))
        return Expr.__ge__(self, other)

    def __lt__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other
        if isinstance(other, NumberSymbol):
            return other.__ge__(self)
        if other.is_real and other.is_number:
            other = other.evalf()
        if isinstance(other, Number):
            return bool(mlib.mpf_lt(self._mpf_, other._as_mpf_val(self._prec)))
        return Expr.__lt__(self, other)

    def __le__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  -->  ! <=
        if isinstance(other, NumberSymbol):
            return other.__gt__(self)
        if other.is_real and other.is_number:
            other = other.evalf()
        if isinstance(other, Number):
            return bool(mlib.mpf_le(self._mpf_, other._as_mpf_val(self._prec)))
        return Expr.__le__(self, other)

    def __hash__(self):
        return super(Float, self).__hash__()

    def epsilon_eq(self, other, epsilon="10e-16"):
        return abs(self - other) < Float(epsilon)

    def _sage_(self):
        import sage.all as sage
        return sage.RealNumber(str(self))

# Add sympify converters
converter[float] = converter[decimal.Decimal] = Float

# this is here to work nicely in Sage
RealNumber = Float


@deprecated(useinstead="Float", issue=1721, deprecated_since_version="0.7.0")
def Real(*args, **kwargs):  # pragma: no cover
    """Deprecated alias for the Float constructor."""
    return Float(*args, **kwargs)


class Rational(Number):
    """Represents integers and rational numbers (p/q) of any size.

    Examples
    ========

    >>> from sympy import Rational, nsimplify, S, pi
    >>> from sympy.abc import x, y
    >>> Rational(3)
    3
    >>> Rational(1, 2)
    1/2

    Rational is unprejudiced in accepting input. If a float is passed, the
    underlying value of the binary representation will be returned:

    >>> Rational(.5)
    1/2
    >>> Rational(.2)
    3602879701896397/18014398509481984

    If the simpler representation of the float is desired then consider
    limiting the denominator to the desired value or convert the float to
    a string (which is roughly equivalent to limiting the denominator to
    10**12):

    >>> Rational(str(.2))
    1/5
    >>> Rational(.2).limit_denominator(10**12)
    1/5

    An arbitrarily precise Rational is obtained when a string literal is
    passed:

    >>> Rational("1.23")
    123/100
    >>> Rational('1e-2')
    1/100
    >>> Rational(".1")
    1/10
    >>> Rational('1e-2/3.2')
    1/320

    The conversion of other types of strings can be handled by
    the sympify() function, and conversion of floats to expressions
    or simple fractions can be handled with nsimplify:

    >>> S('.[3]')  # repeating digits in brackets
    1/3
    >>> S('3**2/10')  # general expressions
    9/10
    >>> nsimplify(.3)  # numbers that have a simple form
    3/10

    But if the input does not reduce to a literal Rational, an error will
    be raised:

    >>> Rational(pi)
    Traceback (most recent call last):
    ...
    TypeError: invalid input: pi


    Low-level
    ---------

    Access numerator and denominator as .p and .q:

    >>> r = Rational(3, 4)
    >>> r
    3/4
    >>> r.p
    3
    >>> r.q
    4

    Note that p and q return integers (not sympy Integers) so some care
    is needed when using them in expressions:

    >>> r.p//r.q
    0

    See Also
    ========
    sympify, sympy.simplify.simplify.nsimplify
    """
    is_real = True
    is_integer = False
    is_rational = True

    __slots__ = ['p', 'q']

    is_Rational = True

    @cacheit
    def __new__(cls, p, q=None):
        if q is None:
            if isinstance(p, Rational):
                return p

            if isinstance(p, basestring):
                p = p.replace(' ', '')
                try:
                    # we might have a Float
                    neg_pow, digits, expt = decimal.Decimal(p).as_tuple()
                    p = [1, -1][neg_pow]*int("".join(str(x) for x in digits))
                    if expt > 0:
                        # TODO: this branch needs a test
                        return Rational(p*Pow(10, expt), 1)
                    return Rational(p, Pow(10, -expt))
                except decimal.InvalidOperation:
                    f = regex.match('^([-+]?[0-9]+)/([0-9]+)$', p)
                    if f:
                        n, d = f.groups()
                        return Rational(int(n), int(d))
                    elif p.count('/') == 1:
                        p, q = p.split('/')
                        return Rational(Rational(p), Rational(q))
                    else:
                        pass  # error will raise below
            else:
                if isinstance(p, decimal.Decimal):
                    rv =  _decimal_to_Rational_prec(p)[0]
                try:
                    if isinstance(p, fractions.Fraction):
                        return Rational(p.numerator, p.denominator)
                except NameError:
                    pass  # error will raise below

                if isinstance(p, (float, Float)):
                    return Rational(*_as_integer_ratio(p))

            if not isinstance(p, SYMPY_INTS + (Rational,)):
                raise TypeError('invalid input: %s' % p)
            q = S.One
        else:
            p = Rational(p)
            q = Rational(q)

        if isinstance(q, Rational):
            p *= q.q
            q = q.p
        if isinstance(p, Rational):
            q *= p.q
            p = p.p

        # p and q are now integers
        if q == 0:
            if p == 0:
                if _errdict["divide"]:
                    raise ValueError("Indeterminate 0/0")
                else:
                    return S.NaN
            if p < 0:
                return S.NegativeInfinity
            return S.Infinity
        if q < 0:
            q = -q
            p = -p
        n = igcd(abs(p), q)
        if n > 1:
            p //= n
            q //= n
        if q == 1:
            return Integer(p)
        if p == 1 and q == 2:
            return S.Half
        obj = Expr.__new__(cls)
        obj.p = p
        obj.q = q
        #obj._args = (p, q)
        return obj

    def limit_denominator(self, max_denominator=1000000):
        """Closest Rational to self with denominator at most max_denominator.

        >>> from sympy import Rational
        >>> Rational('3.141592653589793').limit_denominator(10)
        22/7
        >>> Rational('3.141592653589793').limit_denominator(100)
        311/99

        """
        # Algorithm notes: For any real number x, define a *best upper
        # approximation* to x to be a rational number p/q such that:
        #
        #   (1) p/q >= x, and
        #   (2) if p/q > r/s >= x then s > q, for any rational r/s.
        #
        # Define *best lower approximation* similarly.  Then it can be
        # proved that a rational number is a best upper or lower
        # approximation to x if, and only if, it is a convergent or
        # semiconvergent of the (unique shortest) continued fraction
        # associated to x.
        #
        # To find a best rational approximation with denominator <= M,
        # we find the best upper and lower approximations with
        # denominator <= M and take whichever of these is closer to x.
        # In the event of a tie, the bound with smaller denominator is
        # chosen.  If both denominators are equal (which can happen
        # only when max_denominator == 1 and self is midway between
        # two integers) the lower bound---i.e., the floor of self, is
        # taken.

        if max_denominator < 1:
            raise ValueError("max_denominator should be at least 1")
        if self.q <= max_denominator:
            return self

        p0, q0, p1, q1 = 0, 1, 1, 0
        n, d = self.p, self.q
        while True:
            a = n//d
            q2 = q0 + a*q1
            if q2 > max_denominator:
                break
            p0, q0, p1, q1 = p1, q1, p0 + a*p1, q2
            n, d = d, n - a*d

        k = (max_denominator - q0)//q1
        bound1 = Rational(p0 + k*p1, q0 + k*q1)
        bound2 = Rational(p1, q1)
        if abs(bound2 - self) <= abs(bound1 - self):
            return bound2
        else:
            return bound1

    def __getnewargs__(self):
        return (self.p, self.q)

    def _hashable_content(self):
        return (self.p, self.q)

    def _eval_is_positive(self):
        return self.p > 0

    def _eval_is_zero(self):
        return self.p == 0

    def __neg__(self):
        return Rational(-self.p, self.q)

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        if isinstance(other, Rational):
            return Rational(self.p*other.q + self.q*other.p, self.q*other.q)
        elif isinstance(other, Float):
            return other + self
        else:
            return Number.__add__(self, other)

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        if isinstance(other, Rational):
            return Rational(self.p*other.q - self.q*other.p, self.q*other.q)
        elif isinstance(other, Float):
            return -other + self
        else:
            return Number.__sub__(self, other)

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        if isinstance(other, Rational):
            return Rational(self.p*other.p, self.q*other.q)
        elif isinstance(other, Float):
            return other*self
        else:
            return Number.__mul__(self, other)

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        if isinstance(other, Rational):
            return Rational(self.p*other.q, self.q*other.p)
        elif isinstance(other, Float):
            return self*(1/other)
        else:
            return Number.__div__(self, other)

    __truediv__ = __div__

    @_sympifyit('other', NotImplemented)
    def __mod__(self, other):
        if isinstance(other, Rational):
            n = (self.p*other.q) // (other.p*self.q)
            return Rational(self.p*other.q - n*other.p*self.q, self.q*other.q)
        if isinstance(other, Float):
            evalf = self.evalf()
            # In case self.evalf() does not return Float.
            if isinstance(evalf, Float):
                return evalf % other
        return Number.__mod__(self, other)

    @_sympifyit('other', NotImplemented)
    def __rmod__(self, other):
        if isinstance(other, Rational):
            return Rational.__mod__(other, self)
        if isinstance(other, Float):
            return other % self.evalf()
        return Number.__rmod__(self, other)

    def _eval_power(self, expt):
        if isinstance(expt, Number):
            if isinstance(expt, Float):
                return self._eval_evalf(expt._prec)**expt
            if expt.is_negative:
                # (3/4)**-2 -> (4/3)**2
                ne = -expt
                if (ne is S.One):
                    return Rational(self.q, self.p)
                if self.is_negative:
                    if expt.q != 1:
                        return -(S.NegativeOne)**((expt.p % expt.q) /
                               S(expt.q))*Rational(self.q, -self.p)**ne
                    else:
                        return S.NegativeOne**ne*Rational(self.q, -self.p)**ne
                else:
                    return Rational(self.q, self.p)**ne
            if expt is S.Infinity:  # -oo already caught by test for negative
                if self.p > self.q:
                    # (3/2)**oo -> oo
                    return S.Infinity
                if self.p < -self.q:
                    # (-3/2)**oo -> oo + I*oo
                    return S.Infinity + S.Infinity*S.ImaginaryUnit
                return S.Zero
            if isinstance(expt, Integer):
                # (4/3)**2 -> 4**2 / 3**2
                return Rational(self.p**expt.p, self.q**expt.p)
            if isinstance(expt, Rational):
                if self.p != 1:
                    # (4/3)**(5/6) -> 4**(5/6)*3**(-5/6)
                    return Integer(self.p)**expt*Integer(self.q)**(-expt)
                # as the above caught negative self.p, now self is positive
                return Integer(self.q)**Rational(
                expt.p*(expt.q - 1), expt.q) / \
                    Integer(self.q)**Integer(expt.p)

        if self.is_negative and expt.is_even:
            return (-self)**expt

        return

    def _as_mpf_val(self, prec):
        return mlib.from_rational(self.p, self.q, prec, rnd)

    def _mpmath_(self, prec, rnd):
        return mpmath.make_mpf(mlib.from_rational(self.p, self.q, prec, rnd))

    def __abs__(self):
        return Rational(abs(self.p), self.q)

    def __int__(self):
        p, q = self.p, self.q
        if p < 0:
            return -(-p//q)
        return p//q

    def __eq__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy != other  -->  not ==
        if isinstance(other, NumberSymbol):
            if other.is_irrational:
                return False
            return other.__eq__(self)
        if isinstance(other, Number):
            if isinstance(other, Float):
                return mlib.mpf_eq(self._as_mpf_val(other._prec), other._mpf_)
            elif isinstance(other, Rational):
                return self.p == other.p and self.q == other.q
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  --> not <
        if isinstance(other, NumberSymbol):
            return other.__le__(self)
        if other.is_real and other.is_number and not isinstance(other, Rational):
            other = other.evalf()
        if isinstance(other, Number):
            if isinstance(other, Float):
                return bool(mlib.mpf_gt(
                    self._as_mpf_val(other._prec), other._mpf_))
            return bool(self.p*other.q > self.q*other.p)
        return Expr.__gt__(self, other)

    def __ge__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  -->  not <=
        if isinstance(other, NumberSymbol):
            return other.__lt__(self)
        if other.is_real and other.is_number and not isinstance(other, Rational):
            other = other.evalf()
        if isinstance(other, Number):
            if isinstance(other, Float):
                return bool(mlib.mpf_ge(
                    self._as_mpf_val(other._prec), other._mpf_))
            return bool(self.p*other.q >= self.q*other.p)
        return Expr.__ge__(self, other)

    def __lt__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  --> not <
        if isinstance(other, NumberSymbol):
            return other.__ge__(self)
        if other.is_real and other.is_number and not isinstance(other, Rational):
            other = other.evalf()
        if isinstance(other, Number):
            if isinstance(other, Float):
                return bool(mlib.mpf_lt(
                    self._as_mpf_val(other._prec), other._mpf_))
            return bool(self.p*other.q < self.q*other.p)
        return Expr.__lt__(self, other)

    def __le__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  -->  not <=
        if isinstance(other, NumberSymbol):
            return other.__gt__(self)
        if other.is_real and other.is_number and not isinstance(other, Rational):
            other = other.evalf()
        if isinstance(other, Number):
            if other is S.NaN:
                return None
            if isinstance(other, Float):
                return bool(mlib.mpf_le(
                    self._as_mpf_val(other._prec), other._mpf_))
            return bool(self.p*other.q <= self.q*other.p)
        return Expr.__le__(self, other)

    def __hash__(self):
        return super(Rational, self).__hash__()

    def factors(self, limit=None, use_trial=True, use_rho=False,
                use_pm1=False, verbose=False, visual=False):
        """A wrapper to factorint which return factors of self that are
        smaller than limit (or cheap to compute). Special methods of
        factoring are disabled by default so that only trial division is used.
        """
        from sympy.ntheory import factorint

        f = factorint(self.p, limit=limit, use_trial=use_trial,
                      use_rho=use_rho, use_pm1=use_pm1,
                      verbose=verbose).copy()
        f = defaultdict(int, f)
        for p, e in factorint(self.q, limit=limit,
                              use_trial=use_trial,
                              use_rho=use_rho,
                              use_pm1=use_pm1,
                              verbose=verbose).items():
            f[p] += -e

        if len(f) > 1 and 1 in f:
            del f[1]
        if not f:
            f = {1: 1}
        if not visual:
            return dict(f)
        else:
            if -1 in f:
                f.pop(-1)
                args = [S.NegativeOne]
            else:
                args = []
            args.extend([Pow(*i, **{'evaluate':False})
                         for i in sorted(f.items())])
            return Mul(*args, **{'evaluate': False})

    def as_numer_denom(self):
        return Integer(self.p), Integer(self.q)

    def _sage_(self):
        import sage.all as sage
        return sage.Integer(self.p)/sage.Integer(self.q)

    def as_content_primitive(self, radical=False):
        """Return the tuple (R, self/R) where R is the positive Rational
        extracted from self.

        Examples
        ========

        >>> from sympy import S
        >>> (S(-3)/2).as_content_primitive()
        (3/2, -1)

        See docstring of Expr.as_content_primitive for more examples.
        """

        if self:
            if self.is_positive:
                return self, S.One
            return -self, S.NegativeOne
        return S.One, self

# int -> Integer
_intcache = {}


# TODO move this tracing facility to sympy/core/trace.py  ?
def _intcache_printinfo():
    ints = sorted(_intcache.keys())
    nhit = _intcache_hits
    nmiss = _intcache_misses

    if nhit == 0 and nmiss == 0:
        print
        print 'Integer cache statistic was not collected'
        return

    miss_ratio = float(nmiss) / (nhit + nmiss)

    print
    print 'Integer cache statistic'
    print '-----------------------'
    print
    print '#items: %i' % len(ints)
    print
    print ' #hit   #miss               #total'
    print
    print '%5i   %5i (%7.5f %%)   %5i' % (
        nhit, nmiss, miss_ratio*100, nhit + nmiss)
    print
    print ints

_intcache_hits = 0
_intcache_misses = 0


def int_trace(f):
    import os
    if os.getenv('SYMPY_TRACE_INT', 'no').lower() != 'yes':
        return f

    def Integer_tracer(cls, i):
        global _intcache_hits, _intcache_misses

        try:
            _intcache_hits += 1
            return _intcache[i]
        except KeyError:
            _intcache_hits -= 1
            _intcache_misses += 1

            return f(cls, i)

    # also we want to hook our _intcache_printinfo into sys.atexit
    import atexit
    atexit.register(_intcache_printinfo)

    return Integer_tracer


class Integer(Rational):

    q = 1
    is_integer = True

    is_Integer = True

    __slots__ = ['p']

    def _as_mpf_val(self, prec):
        return mlib.from_int(self.p, prec)

    def _mpmath_(self, prec, rnd):
        return mpmath.make_mpf(self._as_mpf_val(prec))

    # TODO caching with decorator, but not to degrade performance
    @int_trace
    def __new__(cls, i):
        if isinstance(i, basestring):
            i = i.replace(' ', '')
        # whereas we cannot, in general, make a Rational from an
        # arbitrary expression, we can make an Integer unambiguously
        # (except when a non-integer expression happens to round to
        # an integer). So we proceed by taking int() of the input and
        # let the int routines determine whether the expression can
        # be made into an int or whether an error should be raised.
        try:
            ival = int(i)
        except TypeError:
            raise TypeError(
                'Integer can only work with integer expressions.')
        try:
            return _intcache[ival]
        except KeyError:
            # We only work with well-behaved integer types. This converts, for
            # example, numpy.int32 instances.
            obj = Expr.__new__(cls)
            obj.p = ival

            _intcache[ival] = obj
            return obj

    def __getnewargs__(self):
        return (self.p,)

    # Arithmetic operations are here for efficiency
    def __int__(self):
        return self.p

    def __neg__(self):
        return Integer(-self.p)

    def __abs__(self):
        if self.p >= 0:
            return self
        else:
            return Integer(-self.p)

    def __divmod__(self, other):
        from containers import Tuple
        if isinstance(other, Integer):
            return Tuple(*(divmod(self.p, other.p)))
        else:
            return Number.__divmod__(self, other)

    def __rdivmod__(self, other):
        from containers import Tuple
        if isinstance(other, (int, long)):
            return Tuple(*(divmod(other, self.p)))
        else:
            try:
                other = Number(other)
            except TypeError:
                msg = "unsupported operand type(s) for divmod(): '%s' and '%s'"
                oname = type(other).__name__
                sname = type(self).__name__
                raise TypeError(msg % (oname, sname))
            return Number.__divmod__(other, self)

    # TODO make it decorator + bytecodehacks?
    def __add__(self, other):
        if isinstance(other, (int, long)):
            return Integer(self.p + other)
        elif isinstance(other, Integer):
            return Integer(self.p + other.p)
        return Rational.__add__(self, other)

    def __radd__(self, other):
        if isinstance(other, (int, long)):
            return Integer(other + self.p)
        return Rational.__add__(self, other)

    def __sub__(self, other):
        if isinstance(other, (int, long)):
            return Integer(self.p - other)
        elif isinstance(other, Integer):
            return Integer(self.p - other.p)
        return Rational.__sub__(self, other)

    def __rsub__(self, other):
        if isinstance(other, (int, long)):
            return Integer(other - self.p)
        return Rational.__rsub__(self, other)

    def __mul__(self, other):
        if isinstance(other, (int, long)):
            return Integer(self.p*other)
        elif isinstance(other, Integer):
            return Integer(self.p*other.p)
        return Rational.__mul__(self, other)

    def __rmul__(self, other):
        if isinstance(other, (int, long)):
            return Integer(other*self.p)
        return Rational.__mul__(self, other)

    def __mod__(self, other):
        if isinstance(other, (int, long)):
            return Integer(self.p % other)
        elif isinstance(other, Integer):
            return Integer(self.p % other.p)
        return Rational.__mod__(self, other)

    def __rmod__(self, other):
        if isinstance(other, (int, long)):
            return Integer(other % self.p)
        elif isinstance(other, Integer):
            return Integer(other.p % self.p)
        return Rational.__rmod__(self, other)

    def __eq__(self, other):
        if isinstance(other, (int, long)):
            return (self.p == other)
        elif isinstance(other, Integer):
            return (self.p == other.p)
        return Rational.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        if isinstance(other, (int, long)):
            return (self.p > other)
        elif isinstance(other, Integer):
            return (self.p > other.p)
        return Rational.__gt__(self, other)

    def __lt__(self, other):
        if isinstance(other, (int, long)):
            return (self.p < other)
        elif isinstance(other, Integer):
            return (self.p < other.p)
        return Rational.__lt__(self, other)

    def __ge__(self, other):
        if isinstance(other, (int, long)):
            return (self.p >= other)
        elif isinstance(other, Integer):
            return (self.p >= other.p)
        return Rational.__ge__(self, other)

    def __le__(self, other):
        if isinstance(other, (int, long)):
            return (self.p <= other)
        elif isinstance(other, Integer):
            return (self.p <= other.p)
        return Rational.__le__(self, other)

    def __hash__(self):
        return super(Integer, self).__hash__()

    def __index__(self):
        return self.p

    ########################################

    def _eval_is_odd(self):
        return bool(self.p % 2)

    def _eval_power(self, expt):
        """
        Tries to do some simplifications on self**expt

        Returns None if no further simplifications can be done

        When exponent is a fraction (so we have for example a square root),
        we try to find a simpler representation by factoring the argument
        up to factors of 2**15, e.g.

          - sqrt(4) becomes 2
          - sqrt(-4) becomes 2*I
          - (2**(3+7)*3**(6+7))**Rational(1,7) becomes 6*18**(3/7)

        Further simplification would require a special call to factorint on
        the argument which is not done here for sake of speed.

        """
        from sympy import perfect_power

        if expt is S.Infinity:
            if self.p > S.One:
                return S.Infinity
            # cases -1, 0, 1 are done in their respective classes
            return S.Infinity + S.ImaginaryUnit*S.Infinity
        if expt is S.NegativeInfinity:
            return Rational(1, self)**S.Infinity
        if not isinstance(expt, Number):
            # simplify when expt is even
            # (-2)**k --> 2**k
            if self.is_negative and expt.is_even:
                return (-self)**expt
        if not isinstance(expt, Rational):
            return
        if expt is S.Half and self.is_negative:
            # we extract I for this special case since everyone is doing so
            return S.ImaginaryUnit*Pow(-self, expt)
        if expt.is_negative:
            # invert base and change sign on exponent
            ne = -expt
            if self.is_negative:
                if expt.q != 1:
                    return -(S.NegativeOne)**((expt.p % expt.q) /
                            S(expt.q))*Rational(1, -self)**ne
                else:
                    return (S.NegativeOne)**ne*Rational(1, -self)**ne
            else:
                return Rational(1, self.p)**ne
        # see if base is a perfect root, sqrt(4) --> 2
        x, xexact = integer_nthroot(abs(self.p), expt.q)
        if xexact:
            # if it's a perfect root we've finished
            result = Integer(x**abs(expt.p))
            if self.is_negative:
                result *= S.NegativeOne**expt
            return result

        # The following is an algorithm where we collect perfect roots
        # from the factors of base.

        # if it's not an nth root, it still might be a perfect power
        b_pos = int(abs(self.p))
        p = perfect_power(b_pos)
        if p is not False:
            dict = {p[0]: p[1]}
        else:
            dict = Integer(self).factors(limit=2**15)

        # now process the dict of factors
        if self.is_negative:
            dict[-1] = 1
        out_int = 1  # integer part
        out_rad = 1  # extracted radicals
        sqr_int = 1
        sqr_gcd = 0
        sqr_dict = {}
        for prime, exponent in dict.items():
            exponent *= expt.p
            # remove multiples of expt.q: (2**12)**(1/10) -> 2*(2**2)**(1/10)
            div_e, div_m = divmod(exponent, expt.q)
            if div_e > 0:
                out_int *= prime**div_e
            if div_m > 0:
                # see if the reduced exponent shares a gcd with e.q
                # (2**2)**(1/10) -> 2**(1/5)
                g = igcd(div_m, expt.q)
                if g != 1:
                    out_rad *= Pow(prime, Rational(div_m//g, expt.q//g))
                else:
                    sqr_dict[prime] = div_m
        # identify gcd of remaining powers
        for p, ex in sqr_dict.iteritems():
            if sqr_gcd == 0:
                sqr_gcd = ex
            else:
                sqr_gcd = igcd(sqr_gcd, ex)
                if sqr_gcd == 1:
                    break
        for k, v in sqr_dict.iteritems():
            sqr_int *= k**(v//sqr_gcd)
        if sqr_int == self and out_int == 1 and out_rad == 1:
            result = None
        else:
            result = out_int*out_rad*Pow(sqr_int, Rational(sqr_gcd, expt.q))
        return result

    def _eval_is_prime(self):
        from sympy.ntheory import isprime

        return isprime(self)

    def as_numer_denom(self):
        return self, S.One

    def __floordiv__(self, other):
        return Integer(self.p // Integer(other).p)

    def __rfloordiv__(self, other):
        return Integer(Integer(other).p // self.p)

# Add sympify converters
converter[int] = converter[long] = Integer


class RationalConstant(Rational):
    """
    Abstract base class for rationals with specific behaviors

    Derived classes must define class attributes p and q and should probably all
    be singletons.
    """
    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)


class IntegerConstant(Integer):
    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)


class Zero(IntegerConstant):
    __metaclass__ = Singleton

    p = 0
    q = 1
    is_positive = False
    is_negative = False
    is_finite = False
    is_zero = True
    is_composite = False

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.Zero

    @staticmethod
    def __neg__():
        return S.Zero


    def _eval_power(self, expt):
        if expt.is_positive:
            return self
        if expt.is_negative:
            return S.Infinity
        if expt.is_real is False:
            return S.NaN
        # infinities are already handled with pos and neg
        # tests above; now throw away leading numbers on Mul
        # exponent
        coeff, terms = expt.as_coeff_Mul()
        if coeff.is_negative:
            return S.Infinity**terms
        if coeff is not S.One:  # there is a Number to discard
            return self**terms

    def _eval_order(self, *symbols):
        # Order(0,x) -> 0
        return self

    def __nonzero__(self):
        return False


class One(IntegerConstant):
    __metaclass__ = Singleton

    p = 1
    q = 1

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.One

    @staticmethod
    def __neg__():
        return S.NegativeOne

    def _eval_power(self, expt):
        return self

    def _eval_order(self, *symbols):
        return

    @staticmethod
    def factors(limit=None, use_trial=True, use_rho=False, use_pm1=False,
                verbose=False, visual=False):
        if visual:
            return S.One
        return {1: 1}


class NegativeOne(IntegerConstant):
    __metaclass__ = Singleton

    p = -1
    q = 1

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.One

    @staticmethod
    def __neg__():
        return S.One

    def _eval_power(self, expt):
        if expt.is_odd:
            return S.NegativeOne
        if expt.is_even:
            return S.One
        if isinstance(expt, Number):
            if isinstance(expt, Float):
                return Float(-1.0)**expt
            if expt is S.NaN:
                return S.NaN
            if expt is S.Infinity or expt is S.NegativeInfinity:
                return S.NaN
            if expt is S.Half:
                return S.ImaginaryUnit
            if isinstance(expt, Rational):
                if expt.q == 2:
                    return S.ImaginaryUnit**Integer(expt.p)
                i, r = divmod(expt.p, expt.q)
                if i:
                    return self**i*self**Rational(r, expt.q)
        return


class Half(RationalConstant):
    __metaclass__ = Singleton

    p = 1
    q = 2

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.Half


class Infinity(Number):
    __metaclass__ = Singleton

    is_commutative = True
    is_positive = True
    is_bounded = False
    is_finite = False
    is_infinitesimal = False
    is_integer = None
    is_rational = None
    is_odd = None

    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        if isinstance(other, Number):
            if other is S.NegativeInfinity or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('-inf'):
                    return S.NaN
                else:
                    return Float('inf')
            else:
                return S.Infinity
        return NotImplemented
    __radd__ = __add__

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        if isinstance(other, Number):
            if other is S.Infinity or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('inf'):
                    return S.NaN
                else:
                    return Float('inf')
            else:
                return S.Infinity
        return NotImplemented

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        if isinstance(other, Number):
            if other is S.Zero or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == 0:
                    return S.NaN
                if other > 0:
                    return Float('inf')
                else:
                    return Float('-inf')
            else:
                if other > 0:
                    return S.Infinity
                else:
                    return S.NegativeInfinity
        return NotImplemented
    __rmul__ = __mul__

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        if isinstance(other, Number):
            if other is S.Infinity or \
                other is S.NegativeInfinity or \
                    other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('-inf') or \
                        other == Float('inf'):
                    return S.NaN
                elif other.is_nonnegative:
                    return Float('inf')
                else:
                    return Float('-inf')
            else:
                if other >= 0:
                    return S.Infinity
                else:
                    return S.NegativeInfinity
        return NotImplemented

    __truediv__ = __div__

    def __abs__(self):
        return S.Infinity

    def __neg__(self):
        return S.NegativeInfinity

    def _eval_power(self, expt):
        """
        ``expt`` is symbolic object but not equal to 0 or 1.

        ================ ======= ==============================
        Expression       Result  Notes
        ================ ======= ==============================
        ``oo ** nan``    ``nan``
        ``oo ** -p``     ``0``   ``p`` is number, ``oo``
        ================ ======= ==============================

        """
        if expt.is_positive:
            return S.Infinity
        if expt.is_negative:
            return S.Zero
        if expt is S.NaN:
            return S.NaN

        if expt.is_number:
            return self**expt.evalf()

    def _as_mpf_val(self, prec):
        return mlib.finf

    def _sage_(self):
        import sage.all as sage
        return sage.oo

    def __hash__(self):
        return super(Infinity, self).__hash__()

    def __eq__(self, other):
        return other is S.Infinity

    def __ne__(self, other):
        return other is not S.Infinity

    def __lt__(self, other):
        return False

    def __le__(self, other):
        return other is S.Infinity

    def __gt__(self, other):
        return other is not S.Infinity

    def __ge__(self, other):
        return True

    def __mod__(self, other):
        return S.NaN

    __rmod__ = __mod__

oo = S.Infinity


class NegativeInfinity(Number):
    __metaclass__ = Singleton

    is_commutative = True
    is_real = True
    is_positive = False
    is_bounded = False
    is_finite = False
    is_infinitesimal = False
    is_integer = None
    is_rational = None

    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        if isinstance(other, Number):
            if other is S.Infinity or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('inf'):
                    return Float('nan')
                else:
                    return Float('-inf')
            else:
                return S.NegativeInfinity
        return NotImplemented
    __radd__ = __add__

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        if isinstance(other, Number):
            if other is S.NegativeInfinity or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('-inf'):
                    return Float('nan')
                else:
                    return Float('-inf')
            else:
                return S.NegativeInfinity
        return NotImplemented

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        if isinstance(other, Number):
            if other is S.Zero or other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other is S.NaN or other.is_zero:
                    return S.NaN
                elif other.is_positive:
                    return Float('-inf')
                else:
                    return Float('inf')
            else:
                if other.is_positive:
                    return S.NegativeInfinity
                else:
                    return S.Infinity
        return NotImplemented
    __rmul__ = __mul__

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        if isinstance(other, Number):
            if other is S.Infinity or \
                other is S.NegativeInfinity or \
                    other is S.NaN:
                return S.NaN
            elif other.is_Float:
                if other == Float('-inf') or \
                    other == Float('inf') or \
                        other is S.NaN:
                    return S.NaN
                elif other.is_nonnegative:
                    return Float('-inf')
                else:
                    return Float('inf')
            else:
                if other >= 0:
                    return S.NegativeInfinity
                else:
                    return S.Infinity
        return NotImplemented

    __truediv__ = __div__

    def __abs__(self):
        return S.Infinity

    def __neg__(self):
        return S.Infinity

    def _eval_power(self, expt):
        """
        ``expt`` is symbolic object but not equal to 0 or 1.

        ================ ======= ==============================
        Expression       Result  Notes
        ================ ======= ==============================
        ``(-oo) ** nan`` ``nan``
        ``(-oo) ** oo``  ``nan``
        ``(-oo) ** -oo`` ``nan``
        ``(-oo) ** e``   ``oo``  ``e`` is positive even integer
        ``(-oo) ** o``   ``-oo`` ``o`` is positive odd integer
        ================ ======= ==============================

        """
        if isinstance(expt, Number):
            if expt is S.NaN or \
                expt is S.Infinity or \
                    expt is S.NegativeInfinity:
                return S.NaN

            if isinstance(expt, Integer) and expt.is_positive:
                if expt.is_odd:
                    return S.NegativeInfinity
                else:
                    return S.Infinity

            return S.NegativeOne**expt*S.Infinity**expt

    def _as_mpf_val(self, prec):
        return mlib.fninf

    def _sage_(self):
        import sage.all as sage
        return -(sage.oo)

    def __hash__(self):
        return super(NegativeInfinity, self).__hash__()

    def __eq__(self, other):
        return other is S.NegativeInfinity

    def __ne__(self, other):
        return other is not S.NegativeInfinity

    def __lt__(self, other):
        return other is not S.NegativeInfinity

    def __le__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __ge__(self, other):
        return other is S.NegativeInfinity


class NaN(Number):
    """
    Not a Number.

    This represents the corresponding data type to floating point nan, which
    is defined in the IEEE 754 floating point standard, and corresponds to the
    Python ``float('nan')``.

    NaN serves as a place holder for numeric values that are indeterminate,
    but not infinite.  Most operations on nan, produce another nan.  Most
    indeterminate forms, such as ``0/0`` or ``oo - oo` produce nan.  Three
    exceptions are ``0**0``, ``1**oo``, and ``oo**0``, which all produce ``1``
    (this is consistent with Python's float).

    NaN is a singleton, and can be accessed by ``S.NaN``, or can be imported
    as ``nan``.

    Examples
    ========

    >>> from sympy import nan, S, oo
    >>> nan is S.NaN
    True
    >>> oo - oo
    nan
    >>> nan + 1
    nan

    References
    ==========

    - http://en.wikipedia.org/wiki/NaN

    """
    __metaclass__ = Singleton

    is_commutative = True
    is_real = None
    is_rational = None
    is_integer = None
    is_comparable = False
    is_finite = None
    is_bounded = None
    is_zero = None
    is_prime = None
    is_positive = None
    is_negative = None

    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)

    @_sympifyit('other', NotImplemented)
    def __add__(self, other):
        return self

    @_sympifyit('other', NotImplemented)
    def __sub__(self, other):
        return self

    @_sympifyit('other', NotImplemented)
    def __mul__(self, other):
        return self

    @_sympifyit('other', NotImplemented)
    def __div__(self, other):
        return self

    __truediv__ = __div__

    def _as_mpf_val(self, prec):
        return _mpf_nan

    def _sage_(self):
        import sage.all as sage
        return sage.NaN

    def __hash__(self):
        return super(NaN, self).__hash__()

    def __eq__(self, other):
        return other is S.NaN

    def __ne__(self, other):
        return other is not S.NaN

    def __gt__(self, other):
        return False

    def __ge__(self, other):
        return False

    def __lt__(self, other):
        return False

    def __le__(self, other):
        return False

nan = S.NaN


class ComplexInfinity(AtomicExpr):
    __metaclass__ = Singleton

    is_commutative = True
    is_bounded = False
    is_real = None
    is_number = False

    __slots__ = []

    def __new__(cls):
        return AtomicExpr.__new__(cls)

    @staticmethod
    def __abs__():
        return S.Infinity

    @staticmethod
    def __neg__():
        return S.ComplexInfinity

    def _eval_power(self, expt):
        if expt is S.ComplexInfinity:
            return S.NaN

        if isinstance(expt, Number):
            if expt is S.Zero:
                return S.NaN
            else:
                if expt.is_positive:
                    return S.ComplexInfinity
                else:
                    return S.Zero

zoo = S.ComplexInfinity


class NumberSymbol(AtomicExpr):

    is_commutative = True
    is_bounded = True
    is_finite = True
    is_number = True

    __slots__ = []

    is_NumberSymbol = True

    def __new__(cls):
        return AtomicExpr.__new__(cls)

    def approximation(self, number_cls):
        """ Return an interval with number_cls endpoints
        that contains the value of NumberSymbol.
        If not implemented, then return None.
        """

    def _eval_evalf(self, prec):
        return Float._new(self._as_mpf_val(prec), prec)

    def __eq__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy != other  -->  not ==
        if self is other:
            return True
        if isinstance(other, Number) and self.is_irrational:
            return False

        return False    # NumberSymbol != non-(Number|self)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  --> not <
        if self is other:
            return False
        if isinstance(other, Number):
            approx = self.approximation_interval(other.__class__)
            if approx is not None:
                l, u = approx
                if other < l:
                    return False
                if other > u:
                    return True
            return self.evalf() < other
        if other.is_real and other.is_number:
            other = other.evalf()
            return self.evalf() < other
        return Expr.__lt__(self, other)

    def __le__(self, other):
        try:
            other = _sympify(other)
        except SympifyError:
            return False    # sympy > other  --> not <=
        if self is other:
            return True
        if other.is_real and other.is_number:
            other = other.evalf()
        if isinstance(other, Number):
            return self.evalf() <= other
        return Expr.__le__(self, other)

    def __gt__(self, other):
        return (-self) < (-other)

    def __ge__(self, other):
        return (-self) <= (-other)

    def __int__(self):
        # subclass with appropriate return value
        raise NotImplementedError

    def __hash__(self):
        return super(NumberSymbol, self).__hash__()


class Exp1(NumberSymbol):
    __metaclass__ = Singleton

    is_real = True
    is_positive = True
    is_negative = False  # XXX Forces is_negative/is_nonnegative
    is_irrational = True

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.Exp1

    def __int__(self):
        return 2

    def _as_mpf_val(self, prec):
        return mpf_e(prec)

    def approximation_interval(self, number_cls):
        if issubclass(number_cls, Integer):
            return (Integer(2), Integer(3))
        elif issubclass(number_cls, Rational):
            pass

    def _eval_power(self, expt):
        return C.exp(expt)

    def _sage_(self):
        import sage.all as sage
        return sage.e
E = S.Exp1


class Pi(NumberSymbol):
    __metaclass__ = Singleton

    is_real = True
    is_positive = True
    is_negative = False
    is_irrational = True

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.Pi

    def __int__(self):
        return 3

    def _as_mpf_val(self, prec):
        return mpf_pi(prec)

    def approximation_interval(self, number_cls):
        if issubclass(number_cls, Integer):
            return (Integer(3), Integer(4))
        elif issubclass(number_cls, Rational):
            return (Rational(223, 71), Rational(22, 7))

    def _sage_(self):
        import sage.all as sage
        return sage.pi
pi = S.Pi


class GoldenRatio(NumberSymbol):
    __metaclass__ = Singleton

    is_real = True
    is_positive = True
    is_negative = False
    is_irrational = True

    __slots__ = []

    def __int__(self):
        return 1

    def _as_mpf_val(self, prec):
         # XXX track down why this has to be increased
        rv = mlib.from_man_exp(phi_fixed(prec + 10), -prec - 10)
        return mpf_norm(rv, prec)

    def _eval_expand_func(self, **hints):
        from sympy import sqrt
        return S.Half + S.Half*sqrt(5)

    def approximation_interval(self, number_cls):
        if issubclass(number_cls, Integer):
            return (S.One, Rational(2))
        elif issubclass(number_cls, Rational):
            pass

    def _sage_(self):
        import sage.all as sage
        return sage.golden_ratio


class EulerGamma(NumberSymbol):
    __metaclass__ = Singleton

    is_real = True
    is_positive = True
    is_negative = False
    is_irrational = None

    __slots__ = []

    def __int__(self):
        return 0

    def _as_mpf_val(self, prec):
         # XXX track down why this has to be increased
        v = mlib.libhyper.euler_fixed(prec + 10)
        rv = mlib.from_man_exp(v, -prec - 10)
        return mpf_norm(rv, prec)

    def approximation_interval(self, number_cls):
        if issubclass(number_cls, Integer):
            return (S.Zero, S.One)
        elif issubclass(number_cls, Rational):
            return (S.Half, Rational(3, 5))

    def _sage_(self):
        import sage.all as sage
        return sage.euler_gamma


class Catalan(NumberSymbol):
    __metaclass__ = Singleton

    is_real = True
    is_positive = True
    is_negative = False
    is_irrational = None

    __slots__ = []

    def __int__(self):
        return 0

    def _as_mpf_val(self, prec):
        # XXX track down why this has to be increased
        v = mlib.catalan_fixed(prec + 10)
        rv = mlib.from_man_exp(v, -prec - 10)
        return mpf_norm(rv, prec)

    def approximation_interval(self, number_cls):
        if issubclass(number_cls, Integer):
            return (S.Zero, S.One)
        elif issubclass(number_cls, Rational):
            return (Rational(9, 10), S.One)

    def _sage_(self):
        import sage.all as sage
        return sage.catalan


class ImaginaryUnit(AtomicExpr):
    __metaclass__ = Singleton

    is_commutative = True
    is_imaginary = True
    is_bounded = True
    is_finite = True
    is_number = True

    __slots__ = []

    @staticmethod
    def __abs__():
        return S.One

    def _eval_evalf(self, prec):
        return self

    def _eval_conjugate(self):
        return -S.ImaginaryUnit

    def _eval_power(self, expt):
        """
        b is I = sqrt(-1)
        e is symbolic object but not equal to 0, 1

        I**r -> (-1)**(r/2) -> exp(r/2*Pi*I) -> sin(Pi*r/2) + cos(Pi*r/2)*I, r is decimal
        I**0 mod 4 -> 1
        I**1 mod 4 -> I
        I**2 mod 4 -> -1
        I**3 mod 4 -> -I
        """

        if isinstance(expt, Number):
            if isinstance(expt, Integer):
                expt = expt.p % 4
                if expt == 0:
                    return S.One
                if expt == 1:
                    return S.ImaginaryUnit
                if expt == 2:
                    return -S.One
                return -S.ImaginaryUnit
            return (S.NegativeOne)**(expt*S.Half)
        return

    def as_base_exp(self):
        return S.NegativeOne, S.Half

    def _sage_(self):
        import sage.all as sage
        return sage.I

I = S.ImaginaryUnit

try:
    # fractions is only available for python 2.6+
    import fractions

    def sympify_fractions(f):
        return Rational(f.numerator, f.denominator)

    converter[fractions.Fraction] = sympify_fractions
except ImportError:
    pass

try:
    if HAS_GMPY == 2:
        import gmpy2 as gmpy
    elif HAS_GMPY == 1:
        import gmpy
    else:
        raise ImportError

    def sympify_mpz(x):
        return Integer(long(x))

    def sympify_mpq(x):
        return Rational(long(x.numerator), long(x.denominator))

    converter[type(gmpy.mpz(1))] = sympify_mpz
    converter[type(gmpy.mpq(1, 2))] = sympify_mpq
except ImportError:
    pass


def sympify_mpmath(x):
    return Expr._from_mpmath(x, x.context.prec)

converter[mpnumeric] = sympify_mpmath


def sympify_complex(a):
    real, imag = map(sympify, (a.real, a.imag))
    return real + S.ImaginaryUnit*imag

converter[complex] = sympify_complex

_intcache[0] = S.Zero
_intcache[1] = S.One
_intcache[-1] = S.NegativeOne

from power import Pow, integer_nthroot
from mul import Mul
Mul.identity = One()
from add import Add
Add.identity = Zero()
