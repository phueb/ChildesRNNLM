from pathlib import Path
import sys

if sys.platform == 'darwin':
    mnt_point = '/Volumes'
elif 'linux' == sys.platform:
    mnt_point = '/media'
else:
    raise SystemExit('Ludwig does not support this platform')


class RemoteDirs:
    root = Path(mnt_point) / 'research_data' / 'StartingAbstract'
    runs = root / 'runs'
    data = root / 'data'


class LocalDirs:
    root = Path(__file__).parent.parent
    src = Path(__file__).parent
    runs = root / 'runs'


class Global:
    debug = False


class Symbols:
    OOV = 'OOV'


class Eval:
    num_evaluations = 10
    context_types = ['ordered']  # none, ordered, shuffled, last
    category_structures = ['sem']  # sem, syn
    cluster_metrics = ['ba']  # ba, f1, ck  # TODO use all these


class Metrics:
    ba_o = 'ba_ordered'
    ba_n = 'ba_none'


class Figs:
    lw = 2
    axlabel_fs = 12
    leg_fs = 10
    dpi = None