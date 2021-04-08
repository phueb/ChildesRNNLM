from dataclasses import dataclass
from typing import Tuple, Union

# specify params to submit here
param2requests = {
    # 'reverse': [True, False],

    'start': ['entropic', 'fragmented', 'singleton'],

}

param2debug = {
    'context_size': 2,
    'num_iterations': (1, 1),
    'num_sentences': 100_000,
}

# default params
param2default = {
    'shuffle_sentences': False,
    'corpus': 'aochildes',  # or aonewsela
    'num_types': 8000,  # lower than 8K preserves age-order effect but reduces balanced accuracy
    'num_parts': 8,  # the lower the better performance, and age-order effect occurs across num_parts=2-256
    'context_size': 7,  # number of backprop-through-time steps, 7 is better than lower or higher
    'num_sentences': None,  # all sentences if None
    'start': 'none',

    'flavor': 'srn',  # simple-recurrent
    'hidden_size': 512,
    'num_layers': 1,

    'sliding': False,
    'reverse': False,
    'num_iterations': (12, 12),  # more or less than 12 is worse
    'batch_size': 64,
    'lr': 0.01,
    'optimizer': 'adagrad',

}


@dataclass
class Params:
    """
    this object is loaded at the start of job.main() by calling Params.from_param2val(),
    and is populated by Ludwig with hyper-parameters corresponding to a single job.
    """
    shuffle_sentences: bool
    corpus: str
    num_types: int
    num_parts: int
    context_size: int
    num_sentences: Union[None, int]
    start: str

    flavor: str
    hidden_size: int
    num_layers: int

    reverse: bool
    sliding: bool
    num_iterations: Tuple[int, int]
    batch_size: int
    lr: float
    optimizer: str

    @classmethod
    def from_param2val(cls, param2val):
        kwargs = {k: v for k, v in param2val.items()
                  if k not in ['job_name', 'param_name', 'save_path', 'project_path']}
        return cls(**kwargs)
