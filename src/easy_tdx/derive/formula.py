"""通达信公式解释器（子集，独立实现）。

支持解析并计算通达信公式语言（指标/选股）的常用子集：
- 语句：`NAME: expr;`（输出）、`NAME:= expr;`（中间量）、裸表达式
- 变量：OPEN/HIGH/LOW/CLOSE/VOL/AMOUNT（及别名 O/H/L/C/V）、前期赋值变量
- 运算符：`+ - * /`、比较 `< > <= >= = <>`、逻辑 `AND OR NOT`
- 函数：REF MA EMA SMA SUM HHV LLV STD COUNT CROSS ABS MAX MIN IF RSI BARSLAST
  BARSLASTCOUNT BARSCOUNT HHVBARS LLVBARS BACKSET SUMBARS FILTER/TFILTER
  UPNDAY DOWNNDAY SLOPE VAR DMA CONST SQRT POW LOG LN EXP SIGN MOD INTPART ROUND
  BETWEEN ZIG PEAK TROUGH PEAKBARS TROUGHBARS TR ATR OBV PDI MDI ADX ADXR SAR
  WMA MTM ROC DPO（及别名 IFF AVERAGE STDDEV）

用法::

    from easy_tdx.derive.formula import evaluate
    df = evaluate("MA5: MA(CLOSE,5); GOLD: CROSS(MA(CLOSE,5), MA(CLOSE,20));", bars)

返回结果为各 `:` 输出变量的 DataFrame。语义对齐通达信常见口径。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

__all__ = ["evaluate", "Formula", "FormulaError"]


class FormulaError(ValueError):
    """公式解析或计算错误。"""


# --------------------------------------------------------------------------- #
# 词法
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(
    r"""
    (?P<num>\d+\.\d+|\d+) |
    (?P<id>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<op><=|>=|<>|:=|<|>|=|\+|-|\*|/|,|\(|\)) |
    (?P<ws>\s+)
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise FormulaError(f"无法识别的字符: {text[pos]!r} (位置 {pos})")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        value = m.group()
        tokens.append(("num" if kind == "num" else "id" if kind == "id" else "op", value))
    return tokens


# --------------------------------------------------------------------------- #
# 语法（递归下降）→ AST
# --------------------------------------------------------------------------- #


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self) -> tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise FormulaError("表达式意外结束")
        self.pos += 1
        return tok

    def _expect_op(self, op: str) -> None:
        tok = self._next()
        if tok != ("op", op):
            raise FormulaError(f"期望 {op!r}，实际 {tok[1]!r}")

    def parse(self) -> Any:
        node = self._or()
        tok = self._peek()
        if tok is not None:
            raise FormulaError(f"多余的内容: {tok[1]!r}")
        return node

    def _or(self) -> Any:
        node = self._and()
        while self._peek() == ("id", "OR"):
            self._next()
            node = ("bin", "OR", node, self._and())
        return node

    def _and(self) -> Any:
        node = self._not()
        while self._peek() == ("id", "AND"):
            self._next()
            node = ("bin", "AND", node, self._not())
        return node

    def _not(self) -> Any:
        if self._peek() == ("id", "NOT"):
            self._next()
            return ("not", self._not())
        return self._cmp()

    def _cmp(self) -> Any:
        node = self._add()
        tok = self._peek()
        if tok and tok[0] == "op" and tok[1] in ("<", ">", "<=", ">=", "=", "<>"):
            op = self._next()[1]
            return ("bin", op, node, self._add())
        return node

    def _add(self) -> Any:
        node = self._mul()
        while (tok := self._peek()) and tok[0] == "op" and tok[1] in ("+", "-"):
            op = self._next()[1]
            node = ("bin", op, node, self._mul())
        return node

    def _mul(self) -> Any:
        node = self._unary()
        while (tok := self._peek()) and tok[0] == "op" and tok[1] in ("*", "/"):
            op = self._next()[1]
            node = ("bin", op, node, self._unary())
        return node

    def _unary(self) -> Any:
        tok = self._peek()
        if tok and tok[0] == "op" and tok[1] in ("+", "-"):
            op = self._next()[1]
            return ("unary", op, self._unary())
        return self._primary()

    def _primary(self) -> Any:
        kind, value = self._next()
        if kind == "num":
            return ("num", float(value))
        if kind == "id":
            if self._peek() == ("op", "("):
                self._next()
                args: list[Any] = []
                if self._peek() != ("op", ")"):
                    args.append(self._or())
                    while self._peek() == ("op", ","):
                        self._next()
                        args.append(self._or())
                self._expect_op(")")
                return ("call", value.upper(), args)
            return ("var", value.upper())
        if (kind, value) == ("op", "("):
            node = self._or()
            self._expect_op(")")
            return node
        raise FormulaError(f"意外的符号: {value!r}")


# --------------------------------------------------------------------------- #
# 求值
# --------------------------------------------------------------------------- #

_ALIASES = {"O": "OPEN", "H": "HIGH", "L": "LOW", "C": "CLOSE", "V": "VOL"}


def _series(value: Any, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(float(value), index=index)


def _sma_cn(x: pd.Series, n: int, m: int = 1) -> pd.Series:
    return x.ewm(alpha=m / n, adjust=False).mean()


def _fn_ref(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).shift(int(n))


def _fn_ma(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).rolling(int(n)).mean()


def _fn_ema(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).ewm(span=int(n), adjust=False).mean()


def _fn_sma(x: Any, n: Any, m: Any) -> pd.Series:
    return _sma_cn(_series(x, _INDEX["idx"]), int(n), int(m))


def _fn_sum(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).rolling(int(n)).sum()


def _fn_hhv(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).rolling(int(n)).max()


def _fn_llv(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).rolling(int(n)).min()


def _fn_std(x: Any, n: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).rolling(int(n)).std(ddof=0)


def _fn_count(x: Any, n: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"]).astype(float)
    return (s > 0).rolling(int(n)).sum()


def _fn_cross(a: Any, b: Any) -> pd.Series:
    sa = _series(a, _INDEX["idx"])
    sb = _series(b, _INDEX["idx"])
    return (sa > sb) & (sa.shift(1) <= sb.shift(1))


def _fn_abs(x: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]).abs()


def _fn_max(a: Any, b: Any) -> pd.Series:
    return pd.concat([_series(a, _INDEX["idx"]), _series(b, _INDEX["idx"])], axis=1).max(axis=1)


def _fn_min(a: Any, b: Any) -> pd.Series:
    return pd.concat([_series(a, _INDEX["idx"]), _series(b, _INDEX["idx"])], axis=1).min(axis=1)


def _fn_if(c: Any, a: Any, b: Any) -> pd.Series:
    cond = _series(c, _INDEX["idx"]) > 0
    return _series(a, _INDEX["idx"]).where(cond, _series(b, _INDEX["idx"]))


def _fn_rsi(x: Any, n: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"])
    delta = s.diff()
    gain = _sma_cn(delta.clip(lower=0), int(n))
    total = _sma_cn(delta.abs(), int(n))
    return (gain / total.replace(0, pd.NA) * 100).fillna(0.0)


def _fn_barslast(c: Any) -> pd.Series:
    cond = _series(c, _INDEX["idx"]).astype(bool)
    last = pd.Series(index=cond.index, dtype="float64")
    counter = 0
    for i, flag in enumerate(cond.to_numpy()):
        counter = 0 if flag else counter + 1
        last.iloc[i] = counter
    return last


def _fn_barslastcount(x: Any) -> pd.Series:
    """连续满足 X 的周期数（含当前）。"""
    flags = _series(x, _INDEX["idx"]).astype(bool).to_numpy()
    out = np.zeros(len(flags), dtype="float64")
    counter = 0
    for i, flag in enumerate(flags):
        counter = counter + 1 if flag else 0
        out[i] = counter
    return pd.Series(out, index=_INDEX["idx"])


def _fn_bars_count(x: Any) -> pd.Series:
    """首个有效值到当前的周期数。"""
    return _series(x, _INDEX["idx"]).notna().cumsum().astype("float64")


def _fn_hhvbars(x: Any, n: Any) -> pd.Series:
    """N 周期内最高值距今的周期数（并列取最近的一次）。"""
    vals = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    n = int(n)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        w = vals[max(0, i - n + 1) : i + 1]
        if w.size == 0 or np.all(np.isnan(w)):
            continue
        peaks = np.where(w == np.nanmax(w))[0]
        out[i] = w.size - 1 - peaks[-1]
    return pd.Series(out, index=_INDEX["idx"])


def _fn_llvbars(x: Any, n: Any) -> pd.Series:
    """N 周期内最低值距今的周期数（并列取最近的一次）。"""
    vals = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    n = int(n)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        w = vals[max(0, i - n + 1) : i + 1]
        if w.size == 0 or np.all(np.isnan(w)):
            continue
        troughs = np.where(w == np.nanmin(w))[0]
        out[i] = w.size - 1 - troughs[-1]
    return pd.Series(out, index=_INDEX["idx"])


def _fn_backset(x: Any, n: Any) -> pd.Series:
    """X 非 0 时，将当前位置及之前 N-1 个位置置 1。"""
    cond = _series(x, _INDEX["idx"]).astype(bool).to_numpy()
    n = int(n)
    out = np.zeros(len(cond), dtype="float64")
    for i in range(len(cond)):
        if cond[i]:
            out[max(0, i - n + 1) : i + 1] = 1.0
    return pd.Series(out, index=_INDEX["idx"])


def _fn_sumbars(x: Any, n: Any) -> pd.Series:
    """向前累加 X 至 >= N 所需的周期数（含当前；累计不足时返回已用全部周期数）。"""
    vals = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    n = float(n)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        acc = 0.0
        for j in range(i, -1, -1):
            v = vals[j]
            if not np.isnan(v):
                acc += v
            if acc >= n:
                out[i] = i - j + 1
                break
        else:
            out[i] = i + 1
    return pd.Series(out, index=_INDEX["idx"])


def _fn_filter(x: Any, n: Any) -> pd.Series:
    """X 满足输出信号，其后 N 个周期内不再输出（信号本身保留）。"""
    cond = _series(x, _INDEX["idx"]).astype(bool).to_numpy()
    n = int(n)
    out = np.zeros(len(cond), dtype="float64")
    cooldown = 0
    for i in range(len(cond)):
        if cond[i] and cooldown == 0:
            out[i] = 1.0
            cooldown = n
        elif cooldown > 0:
            cooldown -= 1
    return pd.Series(out, index=_INDEX["idx"])


def _fn_upnday(x: Any, n: Any) -> pd.Series:
    """X 连续 N 周期递增。"""
    inc = _series(x, _INDEX["idx"]).diff() > 0
    n = int(n)
    if n <= 1:
        return inc.astype("float64")
    return inc.rolling(n - 1).sum().eq(n - 1).astype("float64")


def _fn_downnday(x: Any, n: Any) -> pd.Series:
    """X 连续 N 周期递减。"""
    dec = _series(x, _INDEX["idx"]).diff() < 0
    n = int(n)
    if n <= 1:
        return dec.astype("float64")
    return dec.rolling(n - 1).sum().eq(n - 1).astype("float64")


def _fn_slope(x: Any, n: Any) -> pd.Series:
    """N 周期线性回归斜率。"""
    n = int(n)
    t = np.arange(n, dtype="float64")
    t_centered = t - t.mean()
    denom = (t_centered**2).sum()

    def _slope(w: np.ndarray) -> float:
        if np.any(np.isnan(w)):
            return float("nan")
        return float((t_centered * (w - w.mean())).sum() / denom)

    return _series(x, _INDEX["idx"]).rolling(n).apply(_slope, raw=True)


def _fn_var(x: Any, n: Any) -> pd.Series:
    """N 周期总体方差。"""
    return _series(x, _INDEX["idx"]).rolling(int(n)).var(ddof=0)


def _fn_dma(x: Any, a: Any) -> pd.Series:
    """动态移动平均：DMA = A*X + (1-A)*DMA[1]。"""
    s = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    weight = _series(a, _INDEX["idx"]).to_numpy(dtype="float64")
    out = np.full(len(s), np.nan)
    prev = np.nan
    for i in range(len(s)):
        out[i] = s[i] if np.isnan(prev) else weight[i] * s[i] + (1 - weight[i]) * prev
        prev = out[i]
    return pd.Series(out, index=_INDEX["idx"])


def _fn_const(x: Any) -> pd.Series:
    """取最后一个有效值为常量填满全序列。"""
    s = _series(x, _INDEX["idx"])
    valid = s.dropna()
    value = float(valid.iloc[-1]) if len(valid) else np.nan
    return pd.Series(value, index=_INDEX["idx"])


def _fn_sqrt(x: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"])
    return np.sqrt(s.where(s >= 0))


def _fn_pow(x: Any, y: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]) ** _series(y, _INDEX["idx"])


def _fn_log(x: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"])
    return np.log10(s.where(s > 0))


def _fn_ln(x: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"])
    return np.log(s.where(s > 0))


def _fn_exp(x: Any) -> pd.Series:
    return np.exp(_series(x, _INDEX["idx"]))


def _fn_sign(x: Any) -> pd.Series:
    return pd.Series(np.sign(_series(x, _INDEX["idx"])), index=_INDEX["idx"])


def _fn_mod(x: Any, y: Any) -> pd.Series:
    return _series(x, _INDEX["idx"]) % _series(y, _INDEX["idx"])


def _fn_intpart(x: Any) -> pd.Series:
    return pd.Series(np.trunc(_series(x, _INDEX["idx"])), index=_INDEX["idx"])


def _fn_round(x: Any, n: Any = 0) -> pd.Series:
    return _series(x, _INDEX["idx"]).round(int(n))


def _fn_between(x: Any, a: Any, b: Any) -> pd.Series:
    s = _series(x, _INDEX["idx"])
    return ((s >= _series(a, _INDEX["idx"])) & (s <= _series(b, _INDEX["idx"]))).astype("float64")


def _zigzag(vals: np.ndarray, pct: float) -> list[tuple[int, float, str]]:
    """百分比阈值之字转向：返回已确认的摆动点 (索引, 值, 'H'/'L')。"""
    n = len(vals)
    pivots: list[tuple[int, float, str]] = []
    if n == 0:
        return pivots
    thr = pct / 100.0
    hi = lo = vals[0]
    hi_i = lo_i = 0
    direction = 0
    ext_val = vals[0]
    ext_i = 0
    i = 0
    while i < n and direction == 0:
        v = vals[i]
        if not np.isnan(v):
            if v > hi:
                hi, hi_i = v, i
            if v < lo:
                lo, lo_i = v, i
            if hi >= vals[0] * (1 + thr):
                direction, ext_val, ext_i = 1, hi, hi_i
            elif lo <= vals[0] * (1 - thr):
                direction, ext_val, ext_i = -1, lo, lo_i
        i += 1
    if direction == 0:
        return pivots
    for j in range(i, n):
        v = vals[j]
        if np.isnan(v):
            continue
        if direction == 1:
            if v > ext_val:
                ext_val, ext_i = v, j
            elif v <= ext_val * (1 - thr):
                pivots.append((ext_i, ext_val, "H"))
                direction, ext_val, ext_i = -1, v, j
        else:
            if v < ext_val:
                ext_val, ext_i = v, j
            elif v >= ext_val * (1 + thr):
                pivots.append((ext_i, ext_val, "L"))
                direction, ext_val, ext_i = 1, v, j
    return pivots


def _swing_series(x: Any, n: Any, m: Any, kind: str, bars: bool) -> pd.Series:
    vals = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    swings = [(i, v) for i, v, k in _zigzag(vals, float(n)) if k == kind]
    m = int(m)
    out = np.full(len(vals), np.nan)
    avail: list[tuple[int, float]] = []
    p = 0
    for i in range(len(vals)):
        while p < len(swings) and swings[p][0] <= i:
            avail.append(swings[p])
            p += 1
        if len(avail) >= m:
            idx_, val_ = avail[-m]
            out[i] = i - idx_ if bars else val_
    return pd.Series(out, index=_INDEX["idx"])


def _fn_zig(x: Any, n: Any) -> pd.Series:
    """百分比之字转向：输出最近已确认摆动点值的阶梯保持线。"""
    vals = _series(x, _INDEX["idx"]).to_numpy(dtype="float64")
    pivots = _zigzag(vals, float(n))
    out = np.full(len(vals), np.nan)
    current = np.nan
    k = 0
    for i in range(len(vals)):
        while k < len(pivots) and pivots[k][0] <= i:
            current = pivots[k][1]
            k += 1
        out[i] = current
    return pd.Series(out, index=_INDEX["idx"])


def _fn_peak(x: Any, n: Any, m: Any = 1) -> pd.Series:
    """前 M 个（自当前回溯）之字峰的值。"""
    return _swing_series(x, n, m, "H", bars=False)


def _fn_trough(x: Any, n: Any, m: Any = 1) -> pd.Series:
    """前 M 个（自当前回溯）之字谷的值。"""
    return _swing_series(x, n, m, "L", bars=False)


def _fn_peakbars(x: Any, n: Any, m: Any = 1) -> pd.Series:
    """前 M 个之字峰距今的周期数。"""
    return _swing_series(x, n, m, "H", bars=True)


def _fn_troughbars(x: Any, n: Any, m: Any = 1) -> pd.Series:
    """前 M 个之字谷距今的周期数。"""
    return _swing_series(x, n, m, "L", bars=True)


def _fn_wma(x: Any, n: Any) -> pd.Series:
    """加权移动平均：权重 1..N（近端权重最大）。"""
    n = int(n)
    weights = np.arange(1, n + 1, dtype="float64")
    denom = weights.sum()
    return (
        _series(x, _INDEX["idx"])
        .rolling(n)
        .apply(lambda w: float((np.asarray(w) * weights).sum() / denom), raw=True)
    )


def _fn_mtm(x: Any, n: Any) -> pd.Series:
    """动量：MTM = X - REF(X, N)。"""
    s = _series(x, _INDEX["idx"])
    return s - s.shift(int(n))


def _fn_roc(x: Any, n: Any) -> pd.Series:
    """变动率：ROC = (X / REF(X, N) - 1) * 100。"""
    s = _series(x, _INDEX["idx"])
    ref = s.shift(int(n))
    return (s / ref.replace(0, pd.NA) - 1) * 100


def _fn_dpo(x: Any, n: Any) -> pd.Series:
    """区间震荡线：DPO = X - REF(MA(X, N), N/2 + 1)。"""
    n = int(n)
    ma = _series(x, _INDEX["idx"]).rolling(n).mean()
    return _series(x, _INDEX["idx"]) - ma.shift(n // 2 + 1)


def _need(name: str) -> pd.Series:
    """取当前求值环境的行情列（供无参指标函数使用）。"""
    if name in _ENV:
        return _ENV[name]
    raise FormulaError(f"缺少行情列: {name}")


def _tr() -> pd.Series:
    high = _need("HIGH")
    low = _need("LOW")
    close = _need("CLOSE")
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def _fn_tr() -> pd.Series:
    """真实波幅 TR = max(H-L, |H-昨收|, |L-昨收|)。"""
    return _tr()


def _fn_atr(n: Any) -> pd.Series:
    """平均真实波幅 ATR = TR 的 N 周期简单均值。"""
    return _tr().rolling(int(n)).mean()


def _fn_obv() -> pd.Series:
    """能量潮 OBV：收涨累加成交量，收跌累减，平盘不变。"""
    close = _need("CLOSE")
    vol = _need("VOL")
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * vol).cumsum()


def _directional(n: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    high, low = _need("HIGH"), _need("LOW")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = _sma_cn(_tr(), n)
    pdi = 100 * _sma_cn(plus_dm, n) / atr.replace(0, pd.NA)
    mdi = 100 * _sma_cn(minus_dm, n) / atr.replace(0, pd.NA)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, pd.NA)
    return pdi.fillna(0.0), mdi.fillna(0.0), dx.fillna(0.0)


def _fn_pdi(n: Any) -> pd.Series:
    """正向动向指标 PDI(N)。"""
    return _directional(int(n))[0]


def _fn_mdi(n: Any) -> pd.Series:
    """负向动向指标 MDI(N)。"""
    return _directional(int(n))[1]


def _fn_adx(n: Any) -> pd.Series:
    """平均动向指标 ADX(N) = DX 的 N 周期 Wilder 平滑。"""
    return _sma_cn(_directional(int(n))[2], int(n))


def _fn_adxr(n: Any) -> pd.Series:
    """ADX 的均值 ADXR(N) = (ADX + ADX[N]) / 2。"""
    adx = _fn_adx(n)
    return (adx + adx.shift(int(n))) / 2


def _fn_sar(n: Any, s: Any, m: Any) -> pd.Series:
    """抛物线转向 SAR(N, S, M)（近似实现；S、M 为百分比，如 SAR(4,2,20)）。"""
    high = _need("HIGH").to_numpy(dtype="float64")
    low = _need("LOW").to_numpy(dtype="float64")
    length = len(high)
    out = np.full(length, np.nan)
    if length < 2:
        return pd.Series(out, index=_INDEX["idx"])
    step = float(s) / 100.0
    max_af = float(m) / 100.0
    trend = 1
    af = step
    extreme = high[0]
    out[0] = low[0]
    for i in range(1, length):
        cur = out[i - 1] + af * (extreme - out[i - 1])
        if trend == 1:
            if low[i] < cur:
                trend, cur, extreme, af = -1, extreme, low[i], step
            elif high[i] > extreme:
                extreme, af = high[i], min(af + step, max_af)
            cur = min(cur, low[i - 1], low[i])
        else:
            if high[i] > cur:
                trend, cur, extreme, af = 1, extreme, high[i], step
            elif low[i] < extreme:
                extreme, af = low[i], min(af + step, max_af)
            cur = max(cur, high[i - 1], high[i])
        out[i] = cur
    return pd.Series(out, index=_INDEX["idx"])


_FUNCS: dict[str, Any] = {
    "REF": _fn_ref,
    "MA": _fn_ma,
    "EMA": _fn_ema,
    "SMA": _fn_sma,
    "SUM": _fn_sum,
    "HHV": _fn_hhv,
    "LLV": _fn_llv,
    "STD": _fn_std,
    "COUNT": _fn_count,
    "CROSS": _fn_cross,
    "ABS": _fn_abs,
    "MAX": _fn_max,
    "MIN": _fn_min,
    "IF": _fn_if,
    "RSI": _fn_rsi,
    "BARSLAST": _fn_barslast,
    "BARSLASTCOUNT": _fn_barslastcount,
    "BARSCOUNT": _fn_bars_count,
    "HHVBARS": _fn_hhvbars,
    "LLVBARS": _fn_llvbars,
    "BACKSET": _fn_backset,
    "SUMBARS": _fn_sumbars,
    "FILTER": _fn_filter,
    "TFILTER": _fn_filter,
    "UPNDAY": _fn_upnday,
    "DOWNNDAY": _fn_downnday,
    "SLOPE": _fn_slope,
    "VAR": _fn_var,
    "DMA": _fn_dma,
    "CONST": _fn_const,
    "SQRT": _fn_sqrt,
    "POW": _fn_pow,
    "LOG": _fn_log,
    "LN": _fn_ln,
    "EXP": _fn_exp,
    "SIGN": _fn_sign,
    "MOD": _fn_mod,
    "INTPART": _fn_intpart,
    "ROUND": _fn_round,
    "BETWEEN": _fn_between,
    "ZIG": _fn_zig,
    "PEAK": _fn_peak,
    "TROUGH": _fn_trough,
    "PEAKBARS": _fn_peakbars,
    "TROUGHBARS": _fn_troughbars,
    "TR": _fn_tr,
    "ATR": _fn_atr,
    "OBV": _fn_obv,
    "PDI": _fn_pdi,
    "MDI": _fn_mdi,
    "ADX": _fn_adx,
    "ADXR": _fn_adxr,
    "SAR": _fn_sar,
    "WMA": _fn_wma,
    "MTM": _fn_mtm,
    "ROC": _fn_roc,
    "DPO": _fn_dpo,
    # 别名
    "IFF": _fn_if,
    "AVERAGE": _fn_ma,
    "STDDEV": _fn_std,
}

# 供函数取用当前数据索引（求值期间设置）
_INDEX: dict[str, pd.Index] = {}
# 供无参指标函数（OBV/ATR/PDI/SAR 等）取用行情列（求值期间设置）
_ENV: dict[str, Any] = {}


def _eval(node: Any, env: dict[str, Any], index: pd.Index) -> Any:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        name = node[1]
        if name in env:
            return env[name]
        raise FormulaError(f"未定义变量: {name}")
    if kind == "call":
        fname, argn = node[1], node[2]
        if fname not in _FUNCS:
            raise FormulaError(f"未知函数: {fname}")
        args = [_eval(a, env, index) for a in argn]
        return _FUNCS[fname](*args)
    if kind == "not":
        return ~(_series(_eval(node[1], env, index), index) > 0)
    if kind == "unary":
        val = _series(_eval(node[2], env, index), index)
        return -val if node[1] == "-" else val
    if kind == "bin":
        op = node[1]
        a = _eval(node[2], env, index)
        b = _eval(node[3], env, index)
        return _apply(op, a, b, index)
    raise FormulaError(f"非法节点: {node!r}")


def _apply(op: str, a: Any, b: Any, index: pd.Index) -> Any:
    if op in ("AND", "OR"):
        sa = _series(a, index) > 0
        sb = _series(b, index) > 0
        return sa & sb if op == "AND" else sa | sb
    sa = _series(a, index)
    sb = _series(b, index)
    if op == "+":
        return sa + sb
    if op == "-":
        return sa - sb
    if op == "*":
        return sa * sb
    if op == "/":
        return sa / sb
    if op == "<":
        return sa < sb
    if op == ">":
        return sa > sb
    if op == "<=":
        return sa <= sb
    if op == ">=":
        return sa >= sb
    if op == "=":
        return sa == sb
    if op == "<>":
        return sa != sb
    raise FormulaError(f"未知运算符: {op}")


# --------------------------------------------------------------------------- #
# 公式
# --------------------------------------------------------------------------- #

_STMT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(:=|:)\s*(.+)$", re.DOTALL)
_COMMENT_RE = re.compile(r"\{[^}]*\}")


@dataclass
class Formula:
    """编译后的公式。"""

    text: str
    statements: list[tuple[str | None, bool, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        src = _COMMENT_RE.sub("", self.text)
        for raw in src.replace("\n", ";").split(";"):
            stmt = raw.strip()
            if not stmt:
                continue
            m = _STMT_RE.match(stmt)
            if m:
                name, op, expr = m.group(1).upper(), m.group(2), m.group(3)
                is_output = op == ":"
            else:
                name, is_output, expr = None, True, stmt
            self.statements.append((name, is_output, _Parser(_tokenize(expr)).parse()))

    @property
    def outputs(self) -> list[str]:
        return [name for name, is_output, _ in self.statements if is_output and name]

    def eval(self, bars: pd.DataFrame) -> pd.DataFrame:
        index = bars.index
        env: dict[str, Any] = {}
        for col in ("OPEN", "HIGH", "LOW", "CLOSE", "VOL", "AMOUNT"):
            if col in bars.columns:
                env[col] = bars[col].astype(float)
        _INDEX["idx"] = index
        _ENV.clear()
        _ENV.update(env)
        try:
            for name, is_output, node in self.statements:
                value = _eval(node, env, index)
                value = _series(value, index)
                if name:
                    env[name] = value
        finally:
            _INDEX.pop("idx", None)
            _ENV.clear()
        out_cols = {name: env[name] for name, is_output, _ in self.statements if is_output and name}
        return pd.DataFrame(out_cols, index=index)


def evaluate(formula: str, bars: pd.DataFrame) -> pd.DataFrame:
    """解析并计算公式，返回输出变量（``:``）的 DataFrame。

    Args:
        formula: 通达信公式文本。
        bars: 含 open/high/low/close/vol/amount 的行情 DataFrame（列名大小写不敏感）。
    """
    norm = bars.rename(columns={c: str(c).upper() for c in bars.columns})
    return Formula(formula).eval(norm)
