"""Chart palette and Plotly styling.

Values come from a validated palette: the categorical slot order is the
colorblind-safety mechanism, not decoration, so assign slots in order and
never cycle past the ceiling. Sequential (one hue, light to dark) is the
default for magnitude; categorical is only for when the series themselves are
the subject; diverging (blue/red around a neutral gray) is for above/below a
baseline.
"""

from __future__ import annotations

# Categorical slots, in fixed order. Never reorder, never cycle.
CATEGORICAL_LIGHT = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

# Sequential blue, light to dark. Used for magnitude comparisons.
SEQUENTIAL_BLUE = [
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]

# Diverging poles for variance-to-target. Neutral gray midpoint.
DIVERGING_POSITIVE = "#2a78d6"
DIVERGING_NEGATIVE = "#e34948"
NEUTRAL_MID = "#f0efec"

# Status palette - reserved, never reused as a series color, and always
# shipped alongside an icon or label so meaning is never carried by hue.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Chrome and ink.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def sequential_shades(n: int) -> list[str]:
    """n steps of the sequential blue ramp, darkest first.

    Darkest maps to the largest value, so a ranked bar chart reads
    more-is-darker down the page.
    """
    if n <= 0:
        return []
    ramp = SEQUENTIAL_BLUE[3:]  # skip the palest steps: they vanish on white
    if n == 1:
        return [ramp[1]]
    step = (len(ramp) - 1) / (n - 1)
    return [ramp[min(len(ramp) - 1, round(i * step))] for i in range(n)][::-1]


def categorical(n: int) -> list[str]:
    """First n categorical slots, in order.

    Raises past the token ceiling rather than generating a hue - a generated
    9th color is indistinguishable from an existing one under colorblindness.
    Fold the tail into 'Other' or facet instead.
    """
    if n > len(CATEGORICAL_LIGHT):
        raise ValueError(
            f"{n} series exceeds the {len(CATEGORICAL_LIGHT)}-slot ceiling; "
            "fold the tail into 'Other' or use small multiples"
        )
    return CATEGORICAL_LIGHT[:n]


def apply_layout(fig, *, height: int = 320, showlegend: bool = False):
    """Shared Plotly chrome: recessive grid, no chart junk, quiet axes."""
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT_FAMILY, size=13, color=TEXT_SECONDARY),
        hoverlabel=dict(
            font_family=FONT_FAMILY, font_size=13, bgcolor="#ffffff", bordercolor=BASELINE
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None
        ),
    )
    fig.update_xaxes(
        showgrid=False, showline=True, linecolor=BASELINE, ticks="outside",
        tickcolor=BASELINE, tickfont=dict(color=TEXT_MUTED), title=None,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRIDLINE, griddash="dot", zeroline=False,
        showline=False, tickfont=dict(color=TEXT_MUTED), title=None,
    )
    return fig
