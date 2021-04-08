import time
import pyprind
import pandas as pd
import numpy as np
import torch
from collections import defaultdict
from pathlib import Path
from itertools import chain
from typing import List
import random

from aochildes.dataset import ChildesDataSet
from preppy import Prep
from entropicstart.editor import Editor

from childesrnnlm import configs
from childesrnnlm.bpe import train_bpe_tokenizer
from childesrnnlm.io import load_probe2cat
from childesrnnlm.evaluation import update_ba_performance
from childesrnnlm.evaluation import update_pp_performance
from childesrnnlm.evaluation import update_dp_performance
from childesrnnlm.evaluation import update_cs_performance
from childesrnnlm.evaluation import update_si_performance
from childesrnnlm.evaluation import update_sd_performance
from childesrnnlm.params import Params
from childesrnnlm.rnn import RNN


def main(param2val):
    # params
    params = Params.from_param2val(param2val)
    print(params)

    project_path = Path(param2val['project_path'])

    # load corpus
    if params.corpus == 'aochildes':
        _sentences = ChildesDataSet().load_sentences()
    elif params.corpus == 'newsela':
        raise NotImplementedError
    else:
        raise AttributeError('Invalid corpus')

    if params.num_sentences:
        _sentences = _sentences[:params.num_sentences]

    # shuffle at sentence level -removes clustering of same-age sentences within parts, when training in shuffled order
    if params.shuffle_sentences:
        random.shuffle(_sentences)

    text_original = ' '.join(_sentences)
    tokens_original = text_original.split()

    # collect all probes, they should be treated as whole words by tokenizer
    probes_in_data = set()
    num_total = 0
    types_in_sentences = set(tokens_original)
    for structure in configs.Eval.structures:
        probe2cat = load_probe2cat(project_path, structure, params.corpus)
        num_total += len(probe2cat)
        for probe in probe2cat.keys():
            if probe in types_in_sentences:
                probes_in_data.add(probe)
            else:
                print(f'"{probe:<24}" not in raw data. Excluded.')
        print(f'structure={structure:<24} | {len(probes_in_data)} of {num_total} total probes occur in raw data')
    special_tokens = list(probes_in_data)  # special tokens should never be split
    for special_token in special_tokens:
        assert special_token in text_original

    # tokenize text
    tokenizer = train_bpe_tokenizer(_sentences, params.num_types, special_tokens=special_tokens)
    print('Tokenizing text..', flush=True)
    tokens = []
    for s in _sentences:
        if tokenizer is not None:
            # TODO try without stripping space symbol
            tokenized_s: List[str] = [t.lstrip('Ġ').strip() for t in tokenizer.encode(s, add_special_tokens=True).tokens
                                      if t not in {'Ġ', '', ' '}]
        else:
            tokenized_s: List[str] = s.split()
        tokens.extend(tokenized_s)
    print(f'{len(set(tokens)):,} types in tokenized text', flush=True)
    print(f'Added {len(tokens) - len(tokens_original):,} tokens during tokenization')

    # check that added tokens were not split during tokenization
    num_errors = 0
    for special_t in special_tokens:
        if special_t not in tokens and special_t in tokens_original:
            print(f'"{special_t:<24}" occurs {tokens_original.count(special_t)} times in original text '
                  f'but not in tokenized text.')
            num_errors += 1
    if num_errors:
        raise RuntimeError(f'{num_errors} special tokens were not found in tokenized text.')

    # prepare data for batching
    prep = Prep(tokens,
                reverse=params.reverse,
                sliding=params.sliding,
                num_parts=params.num_parts,
                num_iterations=params.num_iterations,
                batch_size=params.batch_size,
                context_size=params.context_size,
                shuffle_within_part=False,
                min_num_test_tokens=configs.Eval.min_num_test_tokens,
                disallow_non_ascii=True,
                )

    # prepare artificially generated start sequences for batching
    if params.start != 'none':
        print(f'Adding {params.start} start', flush=True)
        editor = Editor(tokens, special_tokens, num_parts=params.num_parts)
        tokens_start = editor.make_start_tokens(params.start)
        prep_start = Prep(tokens_start,
                          reverse=False,
                          sliding=False,
                          num_parts=1,
                          num_iterations=params.num_iterations,
                          batch_size=params.batch_size,
                          context_size=params.context_size,
                          token2id=prep.token2id
                          )
        assert prep_start.token2id == prep.token2id
        print(f'First {prep_start.num_mbs} batches are reserved for start sentences')
    else:
        prep_start = None
        print(f'Not adding start.')

    # combine start sequences and regular sequences
    if prep_start:
        batch_generator = chain(prep_start.generate_batches(), prep.generate_batches())
        high_resolution_eval_steps = list(range(0, prep_start.num_mbs, prep_start.num_mbs // 10))
    else:
        batch_generator = prep.generate_batches()
        high_resolution_eval_steps = list(range(0, 10_000, 1_000))

    # load all structures, for evaluation, each consisting of a dict mapping probe -> category,
    # make sure each probe is actually in the training data (may not be if isolated in test data)
    structure2probe2cat = defaultdict(dict)
    for structure in configs.Eval.structures:
        probe2cat = load_probe2cat(project_path, structure, params.corpus)
        for probe, cat in probe2cat.items():
            if probe not in probes_in_data:
                continue

            num_in_train = prep.tokens_train.count(probe)
            num_in_valid = prep.tokens_valid.count(probe)
            if num_in_train == 0:
                if num_in_valid == 0:
                    raise RuntimeError(f'"{probe:<24}" not in train or test data after tokenization.')

            else:
                structure2probe2cat[structure][probe] = cat

    # model
    model = RNN(
        params.flavor,
        prep.num_types,
        params.hidden_size,
        params.num_layers,
    )

    # loss function
    criterion = torch.nn.CrossEntropyLoss()
    if params.optimizer == 'adagrad':
        optimizer = torch.optim.Adagrad(model.parameters(), lr=params.lr)
    elif params.optimizer == 'sgd':
        optimizer = torch.optim.SGD(model.parameters(), lr=params.lr)
    else:
        raise AttributeError('Invalid arg to "optimizer"')

    # initialize dictionary for collecting performance data
    performance = {'train_pp': [], 'test_pp': []}

    # train and eval
    eval_steps = []  # to keep track when performance is evaluated
    start_train = time.time()
    pbar = pyprind.ProgBar(prep.num_mbs, stream=1)
    for step, windows in enumerate(batch_generator):

        if step != 0:
            x, y = np.split(windows, [prep.context_size], axis=1)
            inputs = torch.cuda.LongTensor(x)
            targets = torch.cuda.LongTensor(np.squeeze(y))

            # forward step
            model.batch_size = len(windows)  # dynamic batch size
            model.train()
            logits = model(inputs)['logits']  # initial hidden state defaults to zero if not provided

            # backward step
            optimizer.zero_grad()  # sets all gradients to zero
            loss = criterion(logits, targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        pbar.update()

        # evaluate performance
        if step % configs.Eval.num_steps_to_eval == 0 \
                or step in high_resolution_eval_steps:  # eval with higher resolution at start
            eval_steps.append(step)
            model.eval()
            performance = update_pp_performance(performance, model, criterion, prep)

            performance = update_ba_performance(performance, model, prep, structure2probe2cat)
            # performance = update_cs_performance(performance, model, prep, structure2probe2cat)  # TODO slow
            performance = update_dp_performance(performance, model, prep, structure2probe2cat)
            # performance = update_si_performance(performance, model, prep, structure2probe2cat)
            # performance = update_sd_performance(performance, model, prep, structure2probe2cat)

            for k, v in performance.items():
                if not v:
                    continue
                print(f'{k: <12}={v[-1]:.2f}')
            print(flush=True)

            # print progress to console
            minutes_elapsed = int(float(time.time() - start_train) / 60)
            print(f'completed step={step:>12,}/{prep.num_mbs:>12,}')
            print(f'minutes elapsed={minutes_elapsed}')
            print(flush=True)

    # collect performance in list of pandas series
    res = []
    for k, v in performance.items():
        if not v:
            continue
        s = pd.Series(v, index=eval_steps)
        s.name = k
        res.append(s)

    return res
