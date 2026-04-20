from strategies.grid.strategy import GridStrategy
from strategies.dca.strategy import DCAStrategy

REGISTRY: dict[str, type] = {
    "grid": GridStrategy,
    "dca":  DCAStrategy,
}
