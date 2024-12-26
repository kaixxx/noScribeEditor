from PyQt6 import QtWidgets, QtGui

class SearchAndReplaceDialog(QtWidgets.QDialog):

    def __init__(self, parent):
        super(SearchAndReplaceDialog, self).__init__(parent)
        self.setWindowTitle("Find and Replace")

        self.layout = QtWidgets.QVBoxLayout(self)

        # Input fields
        self.search_label = QtWidgets.QLabel("Find:")
        self.replace_label = QtWidgets.QLabel("Replace with:")

        self.search_input = QtWidgets.QLineEdit()
        self.replace_input = QtWidgets.QLineEdit()

        # Options
        self.case_sensitive_checkbox = QtWidgets.QCheckBox("Case Sensitive")
        self.whole_word_checkbox = QtWidgets.QCheckBox("Whole Words Only")

        # Buttons
        self.find_button = QtWidgets.QPushButton("Find Next")
        self.replace_button = QtWidgets.QPushButton("Replace")
        self.replace_all_button = QtWidgets.QPushButton("Replace All")
        self.close_button = QtWidgets.QPushButton("Close")

        # Layout setup
        self.layout.addWidget(self.search_label)
        self.layout.addWidget(self.search_input)
        self.layout.addWidget(self.replace_label)
        self.layout.addWidget(self.replace_input)
        self.layout.addWidget(self.case_sensitive_checkbox)
        self.layout.addWidget(self.whole_word_checkbox)
        
        self.button_layout = QtWidgets.QHBoxLayout()
        self.button_layout.addWidget(self.find_button)
        self.button_layout.addWidget(self.replace_button)
        self.button_layout.addWidget(self.replace_all_button)
        self.button_layout.addWidget(self.close_button)
        
        self.layout.addLayout(self.button_layout)

        # Signal connections
        self.find_button.clicked.connect(self.find_next)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close)

        self.search_input.textChanged.connect(self.highlight_all)
    
    #def close(self):
    #    self.parent().remove_highlight_matches()
    #    return super().close()
        
    def closeEvent(self, a0):
        self.parent().remove_highlight_matches()
        return super().closeEvent(a0)

    def find_next(self):
        search_text = self.search_input.text()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        whole_word = self.whole_word_checkbox.isChecked()
        self.parent().find_next(search_text, case_sensitive, whole_word)

    def replace(self):
        search_text = self.search_input.text()
        replace_text = self.replace_input.text()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        whole_word = self.whole_word_checkbox.isChecked()
        self.parent().replace(search_text, replace_text, case_sensitive, whole_word)

    def replace_all(self):
        search_text = self.search_input.text()
        replace_text = self.replace_input.text()
        case_sensitive = self.case_sensitive_checkbox.isChecked()
        whole_word = self.whole_word_checkbox.isChecked()
        self.parent().replace_all(search_text, replace_text, case_sensitive, whole_word)

    def highlight_all(self):
        text = self.search_input.text()
        if text:
            case_sensitive = self.case_sensitive_checkbox.isChecked()
            whole_word = self.whole_word_checkbox.isChecked()
            self.parent().highlight_matches(text, case_sensitive, whole_word)
        else:
            self.parent().remove_highlight_matches()