cd api
Install UV
uv sync
uv pip install git+https://github.com/nari-labs/dia.git
uv pip uninstall onnx protobuf
uv pip install onnx protobuf
uv pip uninstall numpy
uv pip install "numpy<2.0"
cd ..
source api/.venv/bin/activate
python api/app_dia.py
