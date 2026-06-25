"""file-toolbox 命令行总入口。"""

import typer

from file_toolbox import __version__
from file_toolbox.cli.mkdir_cmd import mkdir
from file_toolbox.cli.pdf_cmd import pdf
from file_toolbox.cli.rename_cmd import rename
from file_toolbox.cli.replace_cmd import replace

app = typer.Typer(
    name="file-toolbox",
    help="批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换",
    invoke_without_command=True,
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


# 注册 4 个命令(平铺,避免子 app 嵌套)
app.command(name="rename")(rename)
app.command(name="mkdir")(mkdir)
app.command(name="pdf")(pdf)
app.command(name="replace")(replace)


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


if __name__ == "__main__":
    app()
