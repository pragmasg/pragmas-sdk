# Fixed PRAGMAS template — correlation matrix (Pearson and Spearman)
# Input:  input.csv (uses all numeric columns), params.json {method?}
# Output: results.json + chart_correlations.png/.pdf
suppressMessages({
  library(jsonlite)
  library(ggplot2)
})

params <- if (file.exists("params.json")) fromJSON("params.json") else list()

df <- read.csv("input.csv", stringsAsFactors = FALSE)
num <- df[sapply(df, is.numeric)]
stopifnot(ncol(num) >= 2)

pearson <- cor(num, use = "pairwise.complete.obs", method = "pearson")
spearman <- cor(num, use = "pairwise.complete.obs", method = "spearman")

mat_a_lista <- function(m) {
  setNames(lapply(rownames(m), function(r)
    setNames(as.list(round(m[r, ], 4)), colnames(m))), rownames(m))
}
resultados <- list(
  variables = colnames(num),
  n = nrow(num),
  pearson = mat_a_lista(pearson),
  spearman = mat_a_lista(spearman)
)
write(toJSON(resultados, auto_unbox = TRUE, pretty = TRUE, digits = 6),
      "results.json")

melt <- expand.grid(Var1 = colnames(pearson), Var2 = colnames(pearson))
melt$valor <- as.vector(pearson)
p <- ggplot(melt, aes(Var1, Var2, fill = valor)) +
  geom_tile(color = "white") +
  geom_text(aes(label = sprintf("%.2f", valor)), size = 3) +
  scale_fill_gradient2(low = "#C62828", mid = "white", high = "#1F3A5F",
                       limits = c(-1, 1), name = "r") +
  labs(title = "Correlation matrix (Pearson)", x = NULL, y = NULL) +
  theme_minimal(base_size = 12) +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))
ggsave("chart_correlations.png", p, width = 8, height = 7, dpi = 150)
ggsave("chart_correlations.pdf", p, width = 8, height = 7)
