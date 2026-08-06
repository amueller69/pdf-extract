---
title: "OCR Math Test Document"
author: "Test Suite"
date: "2026-05-26"
geometry: margin=1in
fontsize: 11pt
---

# Part I: Pure Prose

The history of mathematical notation is inseparable from the history of science itself. For centuries, natural philosophers struggled to express relationships between quantities using ordinary language, and it was only with the development of symbolic notation that rapid progress became possible. The transformation was gradual. Francois Viete introduced systematic use of letters for unknowns in the late sixteenth century, and Leibniz and Newton independently developed calculus notation in the seventeenth, though they disagreed bitterly about priority and method.

What made symbolic notation so powerful was not merely economy of expression but the way it enabled manipulation. A string of words describes a relationship; a symbolic expression can be transformed, differentiated, integrated, composed, and inverted. The notation itself becomes a tool for discovery, not just communication. This is why Hardy famously remarked that mathematical proof is ultimately about the manipulation of symbols according to agreed rules, with meaning attached afterward, not before.

The diffusion of mathematical literacy also transformed the social organization of science. When results could be stated compactly in shared notation, correspondence across national and language boundaries became far more effective. A theorem stated in symbols needed no translation. This compression enabled the cumulative character of modern mathematics, where each generation builds directly on the formalized output of its predecessors rather than having to reconstruct meaning from prose descriptions.


# Part II: Prose with Inline Mathematics

Consider a probability space $(\Omega, \mathcal{F}, P)$ where $\Omega$ is the sample space, $\mathcal{F}$ is a sigma-algebra of events, and $P: \mathcal{F} \to [0,1]$ is a probability measure. For any two events $A, B \in \mathcal{F}$ with $P(B) > 0$, the conditional probability is defined as $P(A \mid B) = P(A \cap B) / P(B)$.

A random variable $X: \Omega \to \mathbb{R}$ is said to be integrable if $E[|X|] < \infty$. When $X$ is square-integrable, meaning $E[X^2] < \infty$, we can define its variance as $\text{Var}(X) = E[X^2] - (E[X])^2$, which is always nonnegative. The standard deviation $\sigma = \sqrt{\text{Var}(X)}$ restores units to the original scale of $X$.

In information theory, the entropy of a discrete random variable $X$ taking values in $\mathcal{X}$ is $H(X) = -\sum_{x \in \mathcal{X}} p(x) \log_2 p(x)$, measured in bits when the logarithm is base 2. The entropy is maximized when $X$ is uniformly distributed, attaining the value $\log_2 |\mathcal{X}|$. The mutual information $I(X; Y) = H(X) - H(X \mid Y)$ captures the reduction in uncertainty about $X$ after observing $Y$. When $X$ and $Y$ are independent, $I(X; Y) = 0$.

The central limit theorem states that if $X_1, X_2, \ldots, X_n$ are independent and identically distributed with mean $\mu$ and finite variance $\sigma^2 > 0$, then $\sqrt{n}(\bar{X}_n - \mu) / \sigma \xrightarrow{d} \mathcal{N}(0,1)$ as $n \to \infty$. This convergence in distribution underlies most classical statistical inference, including the construction of $z$-tests and asymptotic confidence intervals of the form $\bar{X}_n \pm z_{\alpha/2} \cdot \sigma / \sqrt{n}$.

Fourier analysis extends these ideas to function spaces. A square-integrable function $f \in L^2([0,1])$ can be expanded as $f(x) = \sum_{n=-\infty}^{\infty} \hat{f}(n) e^{2\pi i n x}$, where the Fourier coefficients $\hat{f}(n) = \int_0^1 f(x) e^{-2\pi i n x} \, dx$ satisfy Parseval's identity: $\|f\|_2^2 = \sum_{n} |\hat{f}(n)|^2$.


# Part III: Display Mathematics

## Single-Line Equations

The quadratic formula for the roots of $ax^2 + bx + c = 0$:

$$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$

Euler's identity, widely regarded as the most beautiful equation in mathematics:

$$e^{i\pi} + 1 = 0$$

The definition of the Riemann integral as a limit of Riemann sums:

$$\int_a^b f(x)\, dx = \lim_{n \to \infty} \sum_{k=1}^{n} f\!\left(a + k\cdot\frac{b-a}{n}\right) \cdot \frac{b-a}{n}$$

Bayes' theorem, fundamental to both statistics and epistemology:

$$P(\theta \mid x) = \frac{P(x \mid \theta)\, P(\theta)}{P(x)}$$

The Gaussian probability density function:

$$f(x \mid \mu, \sigma^2) = \frac{1}{\sqrt{2\pi\sigma^2}} \exp\!\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)$$


## Multi-Line Equation Blocks

The derivation of the variance of a sum of independent random variables uses linearity of expectation and independence to collapse the cross terms:

\begin{align}
\text{Var}\!\left(\sum_{i=1}^n X_i\right)
  &= E\!\left[\left(\sum_{i=1}^n X_i - \sum_{i=1}^n \mu_i\right)^{\!2}\right] \\
  &= E\!\left[\left(\sum_{i=1}^n (X_i - \mu_i)\right)^{\!2}\right] \\
  &= \sum_{i=1}^n \sum_{j=1}^n E[(X_i - \mu_i)(X_j - \mu_j)] \\
  &= \sum_{i=1}^n \text{Var}(X_i) + 2\sum_{i < j} \text{Cov}(X_i, X_j) \\
  &= \sum_{i=1}^n \text{Var}(X_i)
\end{align}

where the last equality holds because independence implies $\text{Cov}(X_i, X_j) = 0$ for $i \neq j$.

The matrix form of ordinary least squares finds the coefficient vector $\hat{\beta}$ minimizing the sum of squared residuals:

\begin{align}
\hat{\beta}
  &= \arg\min_\beta \|y - X\beta\|^2 \\
  &= \arg\min_\beta (y - X\beta)^\top (y - X\beta) \\
  &= \arg\min_\beta \left(y^\top y - 2\beta^\top X^\top y + \beta^\top X^\top X \beta\right)
\end{align}

Setting the gradient equal to zero and solving:

\begin{align}
\frac{\partial}{\partial \beta}\left(y^\top y - 2\beta^\top X^\top y + \beta^\top X^\top X \beta\right) &= 0 \\
-2X^\top y + 2X^\top X \hat{\beta} &= 0 \\
X^\top X \hat{\beta} &= X^\top y \\
\hat{\beta} &= (X^\top X)^{-1} X^\top y
\end{align}

provided $X^\top X$ is invertible, which holds when the columns of $X$ are linearly independent.

A piecewise-defined function illustrating a common case structure in analysis:

$$f(x) = \begin{cases}
  x^2 \sin(1/x) & \text{if } x \neq 0 \\
  0              & \text{if } x = 0
\end{cases}$$

This function is differentiable at $x = 0$ with $f'(0) = 0$, but its derivative $f'$ is not continuous at the origin, providing a standard counterexample to the converse of the mean value theorem.

The Chapman-Kolmogorov equations, which characterize the transition structure of a continuous-time Markov chain, take the form:

\begin{align}
p_{ij}(s + t) &= \sum_{k \in S} p_{ik}(s)\, p_{kj}(t) \quad \text{for all } s, t \geq 0 \\
\frac{d}{dt} p_{ij}(t)\Big|_{t=0} &= q_{ij} \quad (i \neq j) \\
\sum_{j \in S} q_{ij} &= 0 \quad \text{for all } i \in S
\end{align}

where $q_{ij}$ are the off-diagonal entries of the generator matrix $Q$, satisfying $q_{ij} \geq 0$ for $i \neq j$ and $q_{ii} = -\sum_{j \neq i} q_{ij}$.
