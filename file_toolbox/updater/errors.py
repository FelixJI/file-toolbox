"""自更新异常体系。

所有更新相关异常继承 UpdateError,调用方可一处 catch 统一处理,
也可按具体类型区分(网络/校验/替换)。
"""


class UpdateError(Exception):
    """自更新基础异常。"""


class NetworkError(UpdateError):
    """网络请求失败(两源下载都失败)。"""


class ChecksumMismatchError(UpdateError):
    """SHA256 校验不匹配。"""


class ReplaceError(UpdateError):
    """目录替换或回滚失败。"""
