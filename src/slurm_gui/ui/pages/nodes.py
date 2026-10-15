"""Cluster map: every node as a tile, filterable by partition and GPU type."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ...services.cluster_state import ClusterState
from ...slurm.models import Node, Partition
from .. import theme
from ..widgets.common import Dot, label, page_header
from ..widgets.node_map import NodeMap

_ALL = "All partitions"
_ANY_GPU = "Any node"


class NodesPage(QWidget):
    def __init__(self, state: ClusterState) -> None:
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        self.summary = label("", "Muted")
        lay.addLayout(page_header("Nodes", self.summary))

        bar = QHBoxLayout()
        self.partition = QComboBox()
        self.partition.addItem(_ALL)
        self.gpu = QComboBox()
        self.gpu.addItem(_ANY_GPU)
        bar.addWidget(self.partition)
        bar.addWidget(self.gpu)
        bar.addStretch()
        for text, color in (("idle", theme.GREEN), ("mixed", theme.BLUE), ("allocated", theme.VIOLET),
                            ("drain", theme.AMBER), ("down", theme.RED), ("powered down", theme.TEXT_DIM)):
            bar.addWidget(Dot(color))
            bar.addWidget(label(text, "Muted"))
            bar.addSpacing(8)
        lay.addLayout(bar)

        self.map = NodeMap()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.map)
        hl.addStretch()
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

        self.partition.currentTextChanged.connect(lambda _t: self._render())
        self.gpu.currentTextChanged.connect(lambda _t: self._render())
        state.snapshot.connect(lambda _j, _n: self._render())
        state.partitions_changed.connect(self._on_partitions)

    def _on_partitions(self, parts: list[Partition]) -> None:
        current = self.partition.currentText()
        self.partition.blockSignals(True)
        self.partition.clear()
        self.partition.addItem(_ALL)
        default = None
        for p in sorted(parts, key=lambda p: (not p.is_default, p.name)):
            self.partition.addItem(p.name + (" (default)" if p.is_default else ""), p.name)
            default = default or (p.name + " (default)" if p.is_default else None)
        self.partition.setCurrentText(current if current != _ALL else (default or _ALL))
        self.partition.blockSignals(False)
        self._render()

    def _render(self) -> None:
        nodes: list[Node] = self.state.nodes
        types = sorted({n.gpu_type for n in nodes if n.gpu_type})
        if [self.gpu.itemText(i) for i in range(1, self.gpu.count())] != types:
            current = self.gpu.currentText()
            self.gpu.blockSignals(True)
            self.gpu.clear()
            self.gpu.addItems([_ANY_GPU, *types])
            self.gpu.setCurrentText(current)
            self.gpu.blockSignals(False)
        part = self.partition.currentData()
        gpu = self.gpu.currentText()
        shown = [n for n in nodes
                 if (part is None or part in n.partitions) and (gpu == _ANY_GPU or n.gpu_type == gpu)]
        self.map.set_nodes(sorted(shown, key=lambda n: n.name))
        gpus = sum(n.gpus_total for n in shown if not n.is_unavailable)
        free = sum(n.gpus_free for n in shown)
        idle = sum(n.state == "IDLE" and not n.is_unavailable for n in shown)
        self.summary.setText(f"{len(shown)} nodes · {idle} idle · {free}/{gpus} GPUs free")
