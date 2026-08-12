# Fixed PRAGMAS template — outlier detection (IQR + z-score)
# Input:  input.csv, params.json {value_col?, z_threshold?}
# Output: results.json + chart_outliers.png/.pdf
suppressMessages({
  library(jsonlite)
  library(ggplot2)
})

params <- if (file.exists("params.json")) fromJSON("params.json") else list()
value_col <- if (!is.null(params$value_col)) params$value_col else "value"
z_thr <- if (!is.null(params$z_threshold)) as.numeric(params$z_threshold) else 3

df <- read.csv("input.csv", stringsAsFactors = FALSE)
stopifnot(value_col %in% names(df))
x <- as.numeric(df[[value_col]])
x <- x[!is.na(x)]
stopifnot(length(x) > 3)

q <- quantile(x, c(0.25, 0.75))
iqr <- q[2] - q[1]
lim_inf <- q[1] - 1.5 * iqr
lim_sup <- q[2] + 1.5 * iqr
out_iqr <- x[x < lim_inf | x > lim_sup]

z <- (x - mean(x)) / sd(x)
out_z <- x[abs(z) > z_thr]

resultados <- list(
  n = length(x),
  mean = mean(x), median = median(x), sd = sd(x),
  iqr_bounds = list(lower = lim_inf, upper = lim_sup),
  outliers_iqr = list(n = length(out_iqr), values = as.list(head(sort(out_iqr), 50))),
  outliers_zscore = list(threshold = z_thr, n = length(out_z),
                         values = as.list(head(sort(out_z), 50)))
)
write(toJSON(resultados, auto_unbox = TRUE, pretty = TRUE, digits = 6),
      "results.json")

p <- ggplot(data.frame(valor = x), aes(y = valor)) +
  geom_boxplot(fill = "#5F7A9F", outlier.color = "#C62828", outlier.size = 2) +
  labs(title = "Distribution and outliers (IQR)", y = value_col, x = NULL) +
  theme_minimal(base_size = 12) +
  theme(axis.text.x = element_blank())
ggsave("chart_outliers.png", p, width = 6, height = 6, dpi = 150)
ggsave("chart_outliers.pdf", p, width = 6, height = 6)
