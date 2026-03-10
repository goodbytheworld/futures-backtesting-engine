# 1. VaR (Value at Risk)

**VaR — это квантиль распределения убытков.**

Показывает **максимальный ожидаемый убыток при заданной вероятности и горизонте**.

Формально:

[
VaR_\alpha = - Q_\alpha(PnL)
]

где
(Q_\alpha) — α-квантиль распределения PnL.

### Пример

VaR 95 = −$3,000

Интерпретация:

> С вероятностью **95% дневной убыток не превысит $3,000**

или

> В **5% случаев убыток будет больше**

---

### VaR 95

95% confidence level
Используется для:

* ежедневного мониторинга
* операционного risk control

---

### VaR 99

Более экстремальный уровень.

Используется для:

* tail risk
* capital allocation
* risk limits

---

### Как считать

Для интрадей стратегий обычно используют:

**Historical VaR**

[
VaR = quantile(PnL, 1-\alpha)
]

или

**Parametric VaR**

[
VaR = \mu + z_\alpha \sigma
]

где:

* (z_\alpha) — квантиль нормального распределения
* (\sigma) — volatility

Но для торговых стратегий лучше **historical VaR**.

---

### Что показывать в UI

Графики:

* VaR time series
* VaR vs realized loss
* breach events

---

# 2. Expected Shortfall (ES)

**Expected Shortfall = средний убыток в хвосте распределения.**

Также называется:

* CVaR
* Tail Loss

Формально:

[
ES_\alpha = E[PnL | PnL < -VaR_\alpha]
]

---

### Пример

VaR 95 = −$3k
ES 95 = −$5.2k

Интерпретация:

> Если убыток превысил VaR, **средний убыток будет $5.2k**

---

### Почему ES важнее VaR

VaR:

* не показывает **размер хвоста**

ES:

* показывает **глубину tail risk**

Поэтому:

**Basel III использует ES вместо VaR.**

---

### ES 95

Средний убыток **в худших 5% случаев**.

---

### ES 99

Средний убыток **в худших 1% случаев**.

---

### Что показывать

Графики:

* ES time series
* Tail distribution
* VaR vs ES comparison

---

# 3. Drawdown Analysis

Это **path-dependent риск**.

Даже если VaR маленький, стратегия может иметь **долгие серии убытков**.

---

## Equity Curve

Кумулятивный PnL.

Позволяет увидеть:

* regime changes
* equity stagnation
* risk regimes

---

## Drawdown Curve

[
DD_t = \frac{Equity_t - Peak_t}{Peak_t}
]

где

[
Peak_t = max(Equity_{0..t})
]

---

### Maximum Drawdown

[
MDD = min(DD_t)
]

Показывает:

> худшее падение капитала

---

### Drawdown Duration

Сколько времени требуется для восстановления.

Это **критический риск для интрадей стратегий**.

---

## Drawdown Distribution

Распределение глубины просадок.

Показывает:

* typical DD
* tail DD

Можно строить:

* histogram
* CCDF

---

### Важные метрики

Добавь:

* Max DD
* Avg DD
* Median DD
* 95% DD
* DD duration

---

# 4. Rolling Volatility

Показывает **динамику риска во времени**.

Формула:

[
\sigma_t = std(PnL_{t-N:t})
]

обычно:

* 20 дней
* 50 дней
* 100 дней

---

### Что это показывает

* regime shifts
* volatility clustering
* strategy decay

---

### Для интрадей стратегий

Лучше считать:

* rolling **trade PnL volatility**
* rolling **daily PnL volatility**

---

### Графики

* rolling vol
* vol regimes

---

# 5. Stress Tests

Проверка устойчивости стратегии к ухудшению execution и рынка.

Это **очень важный блок для интрадей стратегий.**

---

## Volatility ×2

Имитация:

* high volatility regime

Эффект:

* стопы чаще
* spread wider
* slippage больше

---

## Slippage ×3

Очень реалистичный стресс.

Многие стратегии **умирают именно здесь**.

---

## Commission ×2

Проверка robustness к cost increase.

---

### Как считать

Пересчитать PnL:

[
PnL_{stress} =
PnL - extra_slippage - extra_fees
]

---

### Что показывать

* stressed equity
* stressed Sharpe
* stressed DD

---

# Что ещё стоит добавить (очень желательно)

Для **профессиональной risk панели** не хватает 4 вещей.

---

## 1. Tail distribution

График:

```
PnL histogram
log scale tail
```

Это показывает:

* fat tails
* crash risk

---

## 2. Loss clustering

График:

```
losing streak distribution
```

Показывает:

* серии убытков

Это **очень важно для интрадей стратегий**.

# Итог

**Хорошая базовая архитектура.**

Для полноценной панели портфельного риска желательно добавить:

```
Risk
│
├ VaR
├ Expected Shortfall
├ Drawdown analysis
├ Rolling volatility
├ Stress tests
├ Tail distribution
└ Losing streak analysis
```