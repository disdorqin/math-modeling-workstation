from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    random = np.random.default_rng(20260721)
    rows = 180
    year = np.arange(rows)
    investment = random.normal(50, 12, rows)
    output = 1.8 * investment + 0.4 * year + random.normal(0, 3, rows)
    target = 0.06 * year + 0.35 * investment + 0.22 * output + random.normal(0, 1.2, rows)
    frame = pd.DataFrame(
        {
            "year_index": year,
            "investment": investment,
            "output": output,
            "target": target,
        }
    )
    destination = Path(__file__).parent / "fixtures" / "phase4_synthetic.csv"
    frame.to_csv(destination, index=False)
    print(destination)


if __name__ == "__main__":
    main()

