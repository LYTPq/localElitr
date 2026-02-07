# localElitr

Copy SimulStreaming, online-text-flow, pipeliner, and mt-wrapper GitHub repos into the project directory.
Inside the project, create a directory named Models, download nllb-200-distilled-600M from the hugging face(we will need only the tokenizer)

Convert the model to CTranslate2 format (int8) using this:
ct2-transformers-converter \
  --model facebook/nllb-200-distilled-600M \
  --output_dir models/nllb-200-ct2-int8 \
  --quantization int8
Put this into models.
Also put desired whisper model into separate folder inside Models(you can change structure in the docker.config.yaml)


docker build -t pipeline .
docker run -it --gpus all --net host -v $(pwd)/models:/models pipeline bash

Inside docker:
python3 pipeline.py --config config.docker.yaml > pipeline.sh
bash pipeline.sh   

Start audio rec in a separate terminal:
arecord -f S16_LE -c1 -r 16000 -t raw -D default | nc localhost 12345
You can change the desired languages in config.yaml.


HW requirements:
Both nllb-200-distilled-600M and whisper can work on CPU, though whisper will be quite slow.
My setup was Ubuntu 24.04.3 LTS, Ryzen 7 7840hs, 4060 mobile(8 GB vram), and 32 GB RAM. The best scenario for the laptop is to launch Whisper on the GPU and translation on the CPU. Max translation speed is achieved with CT2 on a GPU, but with Big Whisper models, it requires more than 8 GB VRAM (a large whisper model alone eats 9-10 gb). I will write a more detailed summary about the consumption of GPU and CPU power in different scenarios later.

SW requirements:
NVIDIA Drivers
NVIDIA Container Toolkit 
CUDA
In case of AMD I am pretty sure that only Container Toolkit will be needed.





