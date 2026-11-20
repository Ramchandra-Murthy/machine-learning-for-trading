import nbformat

from apps.portal.execution import notebook_parameter_defaults


def test_parameter_reader_uses_only_tagged_literal_assignments(tmp_path) -> None:
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                "NOT_A_PARAMETER = 99",
                metadata={"tags": []},
            ),
            nbformat.v4.new_code_cell(
                'SEED = 42\nMAX_SYMBOLS = 10\nUSE_GPU = False\nLABEL = "demo"\n'
                "COMPUTED = make_value()",
                metadata={"tags": ["parameters"]},
            ),
        ]
    )
    path = tmp_path / "parameters.ipynb"
    nbformat.write(notebook, path)

    assert notebook_parameter_defaults(path) == {
        "SEED": 42,
        "MAX_SYMBOLS": 10,
        "USE_GPU": False,
        "LABEL": "demo",
    }
