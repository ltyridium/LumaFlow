import pandas as pd
from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import QTableView, QAbstractItemView, QHeaderView

class PandasTableModel(QAbstractTableModel):
    def __init__(self, data=pd.DataFrame()):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Vertical:
                return str(self._data.index[section])
        return None

    def set_data(self, data: pd.DataFrame):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

class DataTableWidget(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = PandasTableModel()
        self.setModel(self.model)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.horizontalHeader().setStretchLastSection(True)

    def set_data(self, df: pd.DataFrame):
        self.model.set_data(df)
