class AppError(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR"):
        """
        创建应用层异常。

        :param message: 错误提示信息。
        :param code: 错误编码。
        """
        self.message = message
        self.code = code
        super().__init__(message)
