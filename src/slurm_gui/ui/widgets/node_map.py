"""Grid of node tiles: border = node state, cells = GPUs (filled when allocated), bar = CPU use."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ...slurm.models import Node
from .. import theme

TILE_W, TILE_H, GAP = 150, 84, 10


class NodeMap(QWidget):
    node_clicked = pyqtSignal(object)   # Node

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[Node] = []
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_nodes(self, nodes: list[Node]) -> None:
        self.nodes = nodes
        self.updateGeometry()
        self.update()

    def _columns(self) -> int:
        return max(1, (self.width() + GAP) // (TILE_W + GAP))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        cols = max(1, (width + GAP) // (TILE_W + GAP))
        rows = (len(self.nodes) + cols - 1) // cols
        return max(TILE_H, rows * (TILE_H + GAP))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(4 * (TILE_W + GAP), self.heightForWidth(4 * (TILE_W + GAP)))

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.setMinimumHeight(self.heightForWidth(self.width()))
        super().resizeEvent(event)

    def _tile(self, i: int) -> QRectF:
        cols = self._columns()
        r, c = divmod(i, cols)
        return QRectF(c * (TILE_W + GAP) + 0.5, r * (TILE_H + GAP) + 0.5, TILE_W, TILE_H)

    def _node_at(self, pos) -> Node | None:
        for i, node in enumerate(self.nodes):
            if self._tile(i).contains(pos.toPointF()):
                return node
        return None

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        name_font = QFont(self.font())
        name_font.setBold(True)
        small = QFont(self.font())
        if self.font().pixelSize() > 0:   # the stylesheet sets sizes in px, so pointSize() is -1
            small.setPixelSize(max(9, round(self.font().pixelSize() * 0.85)))
        else:
            small.setPointSizeF(max(7.0, self.font().pointSizeF() * 0.85))
        for i, node in enumerate(self.nodes):
            r = self._tile(i)
            color = QColor(theme.node_state_color(node.state, node.flags))
            p.setPen(QPen(color, 1.5))
            p.setBrush(QColor(theme.SURFACE))
            p.drawRoundedRect(r, 7, 7)

            p.setFont(name_font)
            p.setPen(QColor(theme.TEXT))
            p.drawText(r.adjusted(10, 7, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, node.name)
            p.setFont(small)
            p.setPen(color)
            state = node.state.lower() + ("+" + "+".join(f.lower() for f in node.flags) if node.flags else "")
            p.drawText(r.adjusted(10, 25, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, state)

            # GPUs: one cell each.
            if node.gpus_total:
                cell, gap = 12.0, 4.0
                x0, y0 = r.left() + 10, r.top() + 46
                fits = int((r.width() - 20 + gap) // (cell + gap))
                for g in range(min(node.gpus_total, fits)):
                    cr = QRectF(x0 + g * (cell + gap), y0, cell, cell)
                    used = g < node.gpus_alloc
                    p.setPen(QPen(QColor(theme.BLUE), 1))
                    p.setBrush(QColor(theme.BLUE) if used else Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(cr, 3, 3)
                p.setPen(QColor(theme.TEXT_MUTED))
                p.drawText(r.adjusted(10, 44, -10, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                           f"{node.gpus_alloc}/{node.gpus_total}")
            # CPU bar.
            if node.cpus_total:
                bar = QRectF(r.left() + 10, r.bottom() - 13, r.width() - 20, 4)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.BORDER))
                p.drawRoundedRect(bar, 2, 2)
                bar.setWidth(bar.width() * node.cpus_alloc / node.cpus_total)
                p.setBrush(QColor(theme.VIOLET))
                p.drawRoundedRect(bar, 2, 2)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        node = self._node_at(event.position().toPoint())
        if node is None:
            QToolTip.hideText()
            return
        lines = [
            f"<b>{node.name}</b>",
            f"State: {node.state}{' + ' + ', '.join(node.flags) if node.flags else ''}",
            f"Partitions: {', '.join(node.partitions)}",
            f"Features: {', '.join(node.features) or '–'}",
            f"CPUs: {node.cpus_alloc}/{node.cpus_total}" + (f" (load {node.cpu_load:.1f})" if node.cpu_load is not None else ""),
            f"Memory: {node.mem_alloc_mb / 1024:.0f}/{node.mem_total_mb / 1024:.0f} GB allocated",
        ]
        if node.gpus_total:
            lines.append(f"GPUs: {node.gpus_alloc}/{node.gpus_total} {node.gpu_type}")
        if node.reason:
            lines.append(f"Reason: {node.reason}")
        QToolTip.showText(event.globalPosition().toPoint(), "<br>".join(lines), self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        node = self._node_at(event.position().toPoint())
        if node is not None:
            self.node_clicked.emit(node)
