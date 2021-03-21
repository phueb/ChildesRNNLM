from dataclasses import dataclass
from typing import Tuple, Union

# specify params to submit here
param2requests = {
    'reverse': [True, False],
    'context_size': [8],
    'hidden_size': [512],

    # TODO lstm
}

param2debug = {
    'context_size': 2,
    'num_iterations': (1, 1),
    'num_sentences': 100_000,
}

# default params
param2default = {
    'shuffle_sentences': False,
    'corpus': 'aochildes',  # or newsela
    'num_types': 8000,
    'num_parts': 256,
    'context_size': 7,  # number of backprop-through-time steps
    'num_sentences': None,  # all sentences if None

    'flavor': 'srn',  # simple-recurrent
    'hidden_size': 512,

    'sliding': False,
    'reverse': False,
    'num_iterations': (16, 16),
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

    flavor: str
    hidden_size: int

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

