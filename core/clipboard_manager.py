import pandas as pd

class ClipboardManager:
    def __init__(self):
        self.clipboard_df = pd.DataFrame()
        self.source_type = None  # 'source' 或 'edit'

    def set_clipboard(self, df, source_type='edit'):
        self.clipboard_df = df.copy()
        self.source_type = source_type

    def get_clipboard(self):
        return self.clipboard_df.copy()

    def get_source_type(self):
        return self.source_type

    def has_data(self):
        return not self.clipboard_df.empty
