# Fixed PRAGMAS template — sales seasonality
# Input:  input.csv (columns: date, value), params.json {date_col?, value_col?}
# Output: results.json + chart_seasonality.png/.pdf
suppressMessages({
  library(jsonlite)
  library(ggplot2)
})

params <- if (file.exists("params.json")) fromJSON("params.json") else list()
date_col <- if (!is.null(params$date_col)) params$date_col else "date"
value_col <- if (!is.null(params$value_col)) params$value_col else "value"

df <- read.csv("input.csv", stringsAsFactors = FALSE)
stopifnot(date_col %in% names(df), value_col %in% names(df))
df$fecha <- as.Date(df[[date_col]])
df$valor <- as.numeric(df[[value_col]])
df <- df[!is.na(df$fecha) & !is.na(df$valor), ]
stopifnot(nrow(df) > 0)

df$mes <- factor(format(df$fecha, "%m"), levels = sprintf("%02d", 1:12))
media_global <- mean(df$valor)
por_mes <- aggregate(valor ~ mes, data = df, FUN = mean)
por_mes$indice <- por_mes$valor / media_global

resultados <- list(
  n = nrow(df),
  global_mean = media_global,
  seasonal_indices = setNames(as.list(round(por_mes$indice, 4)),
                              as.character(por_mes$mes)),
  peak_month = as.character(por_mes$mes[which.max(por_mes$indice)]),
  trough_month = as.character(por_mes$mes[which.min(por_mes$indice)])
)
write(toJSON(resultados, auto_unbox = TRUE, pretty = TRUE, digits = 6),
      "results.json")

p <- ggplot(por_mes, aes(x = mes, y = indice)) +
  geom_col(fill = "#1F3A5F") +
  geom_hline(yintercept = 1, linetype = "dashed", color = "#C62828") +
  labs(title = "Seasonality index by month",
       x = "Month", y = "Index (mean = 1)") +
  theme_minimal(base_size = 12)
ggsave("chart_seasonality.png", p, width = 9, height = 5, dpi = 150)
ggsave("chart_seasonality.pdf", p, width = 9, height = 5)
