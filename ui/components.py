"""Small reusable widgets for primary actions and secondary details."""
import customtkinter as ctk

BUTTON_HEIGHT = 44


class Disclosure(ctk.CTkFrame):
    def __init__(self, master, title):
        super().__init__(master, fg_color='transparent')
        self.title = title
        self.expanded = False
        self.toggle_button = ctk.CTkButton(self, text='+  ' + title, height=34, anchor='w',
            fg_color=('gray85', 'gray23'), hover_color=('gray78', 'gray29'),
            text_color=('gray15', 'gray90'), command=self.toggle)
        self.toggle_button.pack(fill='x')
        self.content = ctk.CTkFrame(self, fg_color='transparent')

    def toggle(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self, expanded):
        self.expanded = expanded
        self.toggle_button.configure(text=('−  ' if expanded else '+  ') + self.title)
        if expanded:
            self.content.pack(fill='both', expand=True, pady=(8, 0))
        else:
            self.content.pack_forget()


class ActionCard(ctk.CTkFrame):
    def __init__(self, master, title, description, action, command):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=19, weight='bold'), anchor='w').grid(
            row=0, column=0, padx=18, pady=(14, 4), sticky='ew')
        self.description = ctk.CTkLabel(self, text=description, justify='left', anchor='nw', wraplength=350)
        self.description.grid(row=1, column=0, padx=18, pady=(0, 10), sticky='nsew')
        self.grid_rowconfigure(1, weight=1)
        self.button = ctk.CTkButton(self, text=action, height=BUTTON_HEIGHT, font=ctk.CTkFont(size=15, weight='bold'), command=command)
        self.button.grid(row=2, column=0, padx=18, pady=(0, 10), sticky='ew')
        self.note = ctk.CTkLabel(self, text='', anchor='w', justify='left', wraplength=350, text_color='gray65')
        self.note.grid(row=3, column=0, padx=18, pady=(0, 12), sticky='ew')
        self.bind('<Configure>', self._wrap)

    def _wrap(self, event):
        width = max(200, event.width - 36)
        if self.description.cget('wraplength') != width:
            self.description.configure(wraplength=width)
            self.note.configure(wraplength=width)
