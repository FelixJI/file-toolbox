"""后台工作线程(QThread)集合。"""

from .pdf_worker import PdfGenerateWorker

__all__ = ["PdfGenerateWorker"]
