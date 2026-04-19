from strategies.grid.strategy import GridStrategy

# Добавь сюда новые стратегии:
#   from strategies.dca.strategy import DCAStrategy
REGISTRY: dict[str, type] = {
    "grid": GridStrategy,
}
