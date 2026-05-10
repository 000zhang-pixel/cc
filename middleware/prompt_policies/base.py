class BaseImagePromptPolicy:
    def __init__(self, model_name: str, handler):
        self.model_name = model_name
        self.handler = handler
