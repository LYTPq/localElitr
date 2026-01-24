# localElitr

Add SimulStreaming, online-text-flow, pipeliner, and mt-wrapper.
Convert the model to CTranslate2 format (int8) using this command:
ct2-transformers-converter \
  --model facebook/nllb-200-distilled-600M \
  --output_dir models/nllb-200-ct2-int8 \
  --quantization int8

Also, ensure you download the tokenizer from Hugging Face.

Inside docker:
python3 pipeline.py --config config.docker.yaml > pipeline.sh
bash pipeline.sh

Start audio rec in a  separate terminal:
arecord -f S16_LE -c1 -r 16000 -t raw -D default | nc localhost 12345
You can change the desired languages in config.yaml.
