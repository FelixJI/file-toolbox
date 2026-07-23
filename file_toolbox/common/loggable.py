"""日志功能混入类（精简版，只依赖标准库 logging）。"""

import logging


class LoggableMixin:
    """日志功能混入类，提供延迟初始化的 logger 属性。

    使用示例:
        class MyService(LoggableMixin):
            def do_something(self):
                self.logger.info("执行操作")

        service = MyService()
        service.logger.info("服务启动")  # logger 在首次访问时创建
    """

    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器（延迟初始化，使用类所在模块名）。"""
        if not hasattr(self, "_logger"):
            self._logger = logging.getLogger(self.__class__.__module__)
        return self._logger
