"""file-toolbox 命令行总入口。"""

import typer

from file_toolbox import __version__
from file_toolbox.cli.invoice_cmd import invoice
from file_toolbox.cli.mkdir_cmd import mkdir
from file_toolbox.cli.op_parser import OpParseError
from file_toolbox.cli.pdf_cmd import pdf
from file_toolbox.cli.rename_cmd import rename
from file_toolbox.cli.replace_cmd import replace

# OpParseError 属于用户输入错误,不应以 Python traceback 暴露给终端用户。
# pretty_exceptions_enable=False 关闭 Typer 对它的彩色堆栈包装,改由这里统一处理。
app = typer.Typer(
    name="file-toolbox",
    help="批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换",
    invoke_without_command=True,
    pretty_exceptions_show_locals=False,
)


@app.command()
def gui():
    """启动图形界面。"""
    try:
        from file_toolbox.gui.main_window import run_gui
    except ImportError as e:
        typer.secho(
            "GUI 不可用,请安装: pip install 'file-toolbox[gui]'", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(1) from e
    run_gui()


# 注册 5 个命令(平铺,避免子 app 嵌套)
app.command(name="rename")(rename)
app.command(name="mkdir")(mkdir)
app.command(name="pdf")(pdf)
app.command(name="replace")(replace)
app.command(name="invoice")(invoice)


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="显示版本"),
):
    """批量文件工具箱。"""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    """CLI 统一入口,把 OpParseError 转成友好中文提示而非 Python traceback。

    `file-toolbox` 命令(pyproject console_script 指向本函数)与
    `python -m file_toolbox` 两条路径都经此入口。
    standalone_mode=False 使 typer.Exit 以异常抛出,便于在此统一处理。
    """
    try:
        app(standalone_mode=False)
    except OpParseError as e:
        typer.secho(f"错误:{e}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from e
    except typer.Exit as e:
        # standalone_mode=False 下 typer.Exit 以异常抛出,按其退出码退出
        raise SystemExit(e.exit_code) from e


if __name__ == "__main__":
    main()
