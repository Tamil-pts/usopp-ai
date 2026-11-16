"""Explicit model installation. Transcription never downloads weights."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
REPOSITORY='Systran/faster-whisper-small'
REVISION='536b0662742c02347bc0e980a01041f333bce120'
FILES=['config.json','model.bin','tokenizer.json','vocabulary.txt']
def main():
    from backend.core.runtime import BASE
    from huggingface_hub import snapshot_download
    parser=argparse.ArgumentParser(description='Install pinned multilingual speech weights locally.')
    parser.add_argument('--directory',type=Path,default=BASE/'local_ai/models/whisper-small')
    args=parser.parse_args();target=args.directory.resolve()
    snapshot_download(REPOSITORY,revision=REVISION,allow_patterns=FILES,local_dir=str(target))
    if any(not (target/f).is_file() for f in FILES):raise RuntimeError('Speech model files are incomplete.')
    (target/'usopp-model.json').write_text(json.dumps({'repository':REPOSITORY,'revision':REVISION,'files':FILES,'license':'MIT'},indent=2),encoding='utf-8')
    print('Multilingual speech model installed:',target)
if __name__=='__main__':main()
