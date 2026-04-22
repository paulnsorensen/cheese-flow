from ortools.linear_solver import pywraplp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def solve_blend_plan() -> dict[str, float | int]:
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("Unable to initialize OR-Tools GLOP solver.")

    cheddar = solver.NumVar(0.0, solver.infinity(), "cheddar")
    gouda = solver.NumVar(0.0, solver.infinity(), "gouda")

    solver.Add(cheddar + 2 * gouda <= 14)
    solver.Add(3 * cheddar - gouda >= 0)
    solver.Add(cheddar - gouda <= 2)
    solver.Maximize(3 * cheddar + 4 * gouda)

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        raise RuntimeError(f"OR-Tools did not reach an optimal solution. status={status}")

    return {
        "status": int(status),
        "cheddar": cheddar.solution_value(),
        "gouda": gouda.solution_value(),
        "objective": solver.Objective().Value(),
    }


def render_tui(result: dict[str, float | int], console: Console) -> None:
    table = Table(title="Milknado blend optimizer", title_justify="left")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Backend", "python + uv")
    table.add_row("Linear solver status", str(result["status"]))
    table.add_row("Cheddar wheels", f"{result['cheddar']:.2f}")
    table.add_row("Gouda wheels", f"{result['gouda']:.2f}")
    table.add_row("Objective", f"{result['objective']:.2f}")

    console.print(
        Panel.fit(
            table,
            title="Milknado",
            subtitle="rich TUI + OR-Tools",
        )
    )


if __name__ == "__main__":
    render_tui(solve_blend_plan(), Console())
