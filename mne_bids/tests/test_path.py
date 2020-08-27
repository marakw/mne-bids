"""Test for the MNE BIDS path functions."""
# Authors: Adam Li <adam2392@gmail.com>
#
# License: BSD (3-clause)
import os
import os.path as op
# This is here to handle mne-python <0.20
import warnings
from pathlib import Path
import shutil

import pytest

with warnings.catch_warnings():
    warnings.filterwarnings(action='ignore',
                            message="can't resolve package",
                            category=ImportWarning)
    import mne

from mne.datasets import testing
from mne.utils import _TempDir

from mne_bids import (get_modalities, get_entity_vals, print_dir_tree,
                      make_bids_folders, BIDSPath,
                      write_raw_bids)
from mne_bids.path import (_parse_ext, get_entities_from_fname,
                           _find_best_candidates, _find_matching_sidecar,
                           _filter_fnames, get_matched_basenames)

subject_id = '01'
session_id = '01'
run = '01'
acq = None
task = 'testing'

bids_basename = BIDSPath(
    subject=subject_id, session=session_id, run=run, acquisition=acq,
    task=task)


@pytest.fixture(scope='session')
def return_bids_test_dir(tmpdir_factory):
    """Return path to a written test BIDS dir."""
    bids_root = str(tmpdir_factory.mktemp('mnebids_utils_test_bids_ds'))
    data_path = testing.data_path()
    raw_fname = op.join(data_path, 'MEG', 'sample',
                        'sample_audvis_trunc_raw.fif')

    event_id = {'Auditory/Left': 1, 'Auditory/Right': 2, 'Visual/Left': 3,
                'Visual/Right': 4, 'Smiley': 5, 'Button': 32}
    events_fname = op.join(data_path, 'MEG', 'sample',
                           'sample_audvis_trunc_raw-eve.fif')

    raw = mne.io.read_raw_fif(raw_fname)
    raw.info['line_freq'] = 60
    # Write multiple runs for test_purposes
    for run_idx in [run, '02']:
        name = bids_basename.copy().update(run=run_idx)
        write_raw_bids(raw, name, bids_root,
                       events_data=events_fname, event_id=event_id,
                       overwrite=True)

    return bids_root


def test_get_keys(return_bids_test_dir):
    """Test getting the datatypes (=modalities) of a dir."""
    modalities = get_modalities(return_bids_test_dir)
    assert modalities == ['meg']


@pytest.mark.parametrize('entity, expected_vals, kwargs',
                         [('bogus', None, None),
                          ('subject', [subject_id], None),
                          ('session', [session_id], None),
                          ('run', [run, '02'], None),
                          ('acquisition', [], None),
                          ('task', [task], None),
                          ('subject', [], dict(ignore_subjects=[subject_id])),
                          ('subject', [], dict(ignore_subjects=subject_id)),
                          ('session', [], dict(ignore_sessions=[session_id])),
                          ('session', [], dict(ignore_sessions=session_id)),
                          ('run', [run], dict(ignore_runs=['02'])),
                          ('run', [run], dict(ignore_runs='02')),
                          ('task', [], dict(ignore_tasks=[task])),
                          ('task', [], dict(ignore_tasks=task)),
                          ('run', [run, '02'], dict(ignore_runs=['bogus']))])
def test_get_entity_vals(entity, expected_vals, kwargs, return_bids_test_dir):
    """Test getting a list of entities."""
    bids_root = return_bids_test_dir
    if kwargs is None:
        kwargs = dict()

    if entity == 'bogus':
        with pytest.raises(ValueError, match='`key` must be one of'):
            get_entity_vals(bids_root=bids_root, entity_key=entity, **kwargs)
    else:
        vals = get_entity_vals(bids_root=bids_root, entity_key=entity,
                               **kwargs)
        assert vals == expected_vals


def test_print_dir_tree(capsys):
    """Test printing a dir tree."""
    with pytest.raises(ValueError, match='Directory does not exist'):
        print_dir_tree('i_dont_exist')

    # We check the testing directory
    test_dir = op.dirname(__file__)
    with pytest.raises(ValueError, match='must be a positive integer'):
        print_dir_tree(test_dir, max_depth=-1)
    with pytest.raises(ValueError, match='must be a positive integer'):
        print_dir_tree(test_dir, max_depth='bad')

    # Do not limit depth
    print_dir_tree(test_dir)
    captured = capsys.readouterr()
    assert '|--- test_utils.py' in captured.out.split('\n')
    assert '|--- __pycache__{}'.format(os.sep) in captured.out.split('\n')
    assert '.pyc' in captured.out

    # Now limit depth ... we should not descend into pycache
    print_dir_tree(test_dir, max_depth=1)
    captured = capsys.readouterr()
    assert '|--- test_utils.py' in captured.out.split('\n')
    assert '|--- __pycache__{}'.format(os.sep) in captured.out.split('\n')
    assert '.pyc' not in captured.out

    # Limit depth even more
    print_dir_tree(test_dir, max_depth=0)
    captured = capsys.readouterr()
    assert captured.out == '|tests{}\n'.format(os.sep)


def test_make_folders():
    """Test that folders are created and named properly."""
    # Make sure folders are created properly
    bids_root = _TempDir()
    make_bids_folders(subject='hi', session='foo', modality='ba',
                      bids_root=bids_root)
    assert op.isdir(op.join(bids_root, 'sub-hi', 'ses-foo', 'ba'))

    # If we remove a kwarg the folder shouldn't be created
    bids_root = _TempDir()
    make_bids_folders(subject='hi', modality='ba', bids_root=bids_root)
    assert op.isdir(op.join(bids_root, 'sub-hi', 'ba'))

    # check overwriting of folders
    make_bids_folders(subject='hi', modality='ba', bids_root=bids_root,
                      overwrite=True, verbose=True)

    # Check if a pathlib.Path bids_root works.
    bids_root = Path(_TempDir())
    make_bids_folders(subject='hi', session='foo', modality='ba',
                      bids_root=bids_root)
    assert op.isdir(op.join(bids_root, 'sub-hi', 'ses-foo', 'ba'))

    # Check if bids_root=None creates folders in the current working directory
    bids_root = _TempDir()
    curr_dir = os.getcwd()
    os.chdir(bids_root)
    make_bids_folders(subject='hi', session='foo', modality='ba',
                      bids_root=None)
    assert op.isdir(op.join(os.getcwd(), 'sub-hi', 'ses-foo', 'ba'))
    os.chdir(curr_dir)


def test_parse_ext():
    """Test the file extension extraction."""
    f = 'sub-05_task-matchingpennies.vhdr'
    fname, ext = _parse_ext(f)
    assert fname == 'sub-05_task-matchingpennies'
    assert ext == '.vhdr'

    # Test for case where no extension: assume BTI format
    f = 'sub-01_task-rest'
    fname, ext = _parse_ext(f)
    assert fname == f
    assert ext == '.pdf'

    # Get a .nii.gz file
    f = 'sub-01_task-rest.nii.gz'
    fname, ext = _parse_ext(f)
    assert fname == 'sub-01_task-rest'
    assert ext == '.nii.gz'


@pytest.mark.parametrize('fname', [
    'sub-01_ses-02_task-test_run-3_split-01_meg.fif',
    'sub-01_ses-02_task-test_run-3_split-01.fif',
    'sub-01_ses-02_task-test_run-3_split-01',
    ('/bids_root/sub-01/ses-02/meg/' +
     'sub-01_ses-02_task-test_run-3_split-01_meg.fif'),
])
def test_parse_bids_filename(fname):
    """Test parsing entities from a bids filename."""
    params = get_entities_from_fname(fname)
    print(params)
    assert params['subject'] == '01'
    assert params['session'] == '02'
    assert params['run'] == '3'
    assert params['task'] == 'test'
    assert params['split'] == '01'
    if 'meg' in fname:
        assert params['suffix'] == 'meg'
    assert list(params.keys()) == ['subject', 'session', 'task',
                                   'acquisition', 'run', 'processing',
                                   'space', 'recording', 'split', 'suffix']


@pytest.mark.parametrize('candidate_list, best_candidates', [
    # Only one candidate
    (['sub-01_ses-02'], ['sub-01_ses-02']),

    # Two candidates, but the second matches on more entities
    (['sub-01', 'sub-01_ses-02'], ['sub-01_ses-02']),

    # No candidates match
    (['sub-02_ses-02', 'sub-01_ses-01'], []),

    # First candidate is disqualified (session doesn't match)
    (['sub-01_ses-01', 'sub-01_ses-02'], ['sub-01_ses-02']),

    # Multiple equally good candidates
    (['sub-01_run-01', 'sub-01_run-02'], ['sub-01_run-01', 'sub-01_run-02']),
])
def test_find_best_candidates(candidate_list, best_candidates):
    """Test matching of candidate sidecar files."""
    params = dict(subject='01', session='02', acquisition=None)
    assert _find_best_candidates(params, candidate_list) == best_candidates


def test_find_matching_sidecar(return_bids_test_dir):
    """Test finding a sidecar file from a BIDS dir."""
    bids_root = return_bids_test_dir

    bids_fpath = bids_basename.copy().update(root=bids_root)

    # Now find a sidecar
    sidecar_fname = _find_matching_sidecar(bids_fpath,
                                           suffix='coordsystem',
                                           extension='.json')
    expected_file = op.join('sub-01', 'ses-01', 'meg',
                            'sub-01_ses-01_coordsystem.json')
    assert sidecar_fname.endswith(expected_file)

    # Find multiple sidecars, tied in score, triggering an error
    with pytest.raises(RuntimeError, match='Expected to find a single'):
        open(sidecar_fname.replace('coordsystem.json',
                                   '2coordsystem.json'), 'w').close()
        print_dir_tree(bids_root)
        _find_matching_sidecar(bids_fpath,
                               suffix='coordsystem', extension='.json')

    # Find nothing but receive None, because we set `allow_fail` to True
    with pytest.warns(RuntimeWarning, match='Did not find any'):
        _find_matching_sidecar(bids_fpath,
                               suffix='foo', extension='.bogus',
                               allow_fail=True)


def test_bids_path_inference(return_bids_test_dir):
    """Test usage of BIDSPath object and fpath."""
    bids_root = return_bids_test_dir

    # without providing all the entities, ambiguous when trying
    # to use fpath
    bids_path = BIDSPath(
        subject=subject_id, session=session_id, acquisition=acq,
        task=task, root=bids_root)
    with pytest.raises(RuntimeError, match='Found more than one'):
        bids_path.fpath

    # can't locate a file, but the basename should work
    bids_path = BIDSPath(
        subject=subject_id, session=session_id, acquisition=acq,
        task=task, run='10', root=bids_root)
    with pytest.warns(RuntimeWarning, match='Could not locate'):
        fpath = bids_path.fpath
        assert str(fpath) == op.join(bids_root, f'sub-{subject_id}',
                                     f'ses-{session_id}',
                                     bids_path.basename)

    # shouldn't error out when there is no uncertainty
    channels_fname = BIDSPath(subject=subject_id, session=session_id,
                              run=run, acquisition=acq, task=task,
                              root=bids_root, suffix='channels')
    channels_fname.fpath

    # create an extra file under 'eeg'
    extra_file = op.join(bids_root, f'sub-{subject_id}',
                         f'ses-{session_id}', 'eeg',
                         channels_fname.basename + '.tsv')
    Path(extra_file).parent.mkdir(exist_ok=True, parents=True)
    # Creates a new file and because of this new file, there is now
    # ambiguity
    with open(extra_file, 'w'):
        pass
    with pytest.raises(RuntimeError, match='Found data of more than one'):
        channels_fname.fpath

    # if you set modality, now there is no ambiguity
    channels_fname.update(modality='eeg')
    assert str(channels_fname.fpath) == extra_file
    # set state back to original
    shutil.rmtree(Path(extra_file).parent)


def test_bids_path(return_bids_test_dir):
    """Test usage of BIDSPath object."""
    bids_root = return_bids_test_dir

    bids_path = BIDSPath(
        subject=subject_id, session=session_id, run=run, acquisition=acq,
        task=task, root=bids_root, suffix='meg')

    expected_parent_dir = op.join(bids_root, f'sub-{subject_id}',
                                  f'ses-{session_id}', 'meg')
    assert str(bids_path.fpath.parent) == expected_parent_dir

    # test bids path without bids_root, suffix, extension
    # basename and fpath should be the same
    expected_basename = f'sub-{subject_id}_ses-{session_id}_task-{task}_run-{run}'  # noqa
    assert (op.basename(bids_path.fpath) ==
            expected_basename + '_meg.fif')
    assert op.dirname(bids_path.fpath).startswith(bids_root)

    # when bids root is not passed in, passes relative path
    bids_path2 = bids_path.copy().update(modality='meg', root=None)
    expected_relpath = op.join(
        f'sub-{subject_id}', f'ses-{session_id}', 'meg',
        expected_basename + '_meg')
    assert str(bids_path2.fpath) == expected_relpath

    # without bids_root and with suffix/extension
    # basename and fpath should be the same
    bids_path.update(suffix='ieeg', extension='vhdr')
    expected_basename2 = expected_basename + '_ieeg.vhdr'
    assert (bids_path.basename == expected_basename2)
    bids_path.update(extension='.vhdr')
    assert (bids_path.basename == expected_basename2)

    # with bids_root, but without suffix/extension
    # basename should work, but fpath should not.
    bids_path.update(root=bids_root, suffix=None, extension=None)
    assert bids_path.basename == expected_basename

    # should find the correct filename if suffix was passed
    bids_path.update(suffix='meg', extension='.fif')
    bids_fpath = bids_path.fpath
    assert op.basename(bids_fpath) == \
           bids_path.basename
    # Same test, but exploiting the fact that bids_fpath is a pathlib.Path
    assert bids_fpath.name == bids_path.basename

    # confirm BIDSPath assigns properties correctly
    bids_basename = BIDSPath(subject=subject_id,
                             session=session_id)
    assert bids_basename.subject == subject_id
    assert bids_basename.session == session_id
    assert 'subject' in bids_basename.entities
    assert 'session' in bids_basename.entities
    print(bids_basename.entities)
    assert all(bids_basename.entities.get(entity) is None
               for entity in ['task', 'run', 'recording', 'acquisition',
                              'space', 'processing', 'split',
                              'root', 'modality',
                              'suffix', 'extension'])

    # test updating functionality
    bids_basename.update(acquisition='03', run='2', session='02',
                         task=None)
    assert bids_basename.subject == subject_id
    assert bids_basename.session == '02'
    assert bids_basename.acquisition == '03'
    assert bids_basename.run == '2'
    assert bids_basename.task is None

    new_bids_basename = bids_basename.copy().update(task='02',
                                                    acquisition=None)
    assert new_bids_basename.task == '02'
    assert new_bids_basename.acquisition is None

    # equality of bids basename
    assert new_bids_basename != bids_basename
    assert new_bids_basename == bids_basename.copy().update(task='02',
                                                            acquisition=None)

    # error check on kwargs of update
    with pytest.raises(ValueError, match='Key must be one of*'):
        bids_basename.update(sub=subject_id, session=session_id)

    # error check on the passed in entity containing a magic char
    with pytest.raises(ValueError, match='Unallowed*'):
        bids_basename.update(subject=subject_id + '-')

    # error check on suffix in BIDSPath (deep check)
    suffix = 'meeg'
    with pytest.raises(ValueError, match=f'Suffix {suffix} is not'):
        BIDSPath(subject=subject_id, session=session_id,
                 suffix=suffix)

    # do error check suffix in update
    error_kind = 'foobar'
    with pytest.raises(ValueError, match=f'Suffix {error_kind} is not'):
        bids_basename.update(suffix=error_kind)

    # does not error check on suffix in BIDSPath (deep check)
    suffix = 'meeg'
    bids_basename = BIDSPath(subject=subject_id, session=session_id,
                             suffix=suffix, check=False)
    # also inherits error check from instantiation
    # always error check modality
    with pytest.raises(ValueError, match='"modality" can only be '
                                         'one of'):
        bids_basename.copy().update(modality=error_kind)

    # suffix won't be error checks if initial check was false
    bids_basename.update(suffix=suffix)

    # error check on extension in BIDSPath (deep check)
    extension = '.mat'
    with pytest.raises(ValueError, match=f'Extension {extension} is not'):
        BIDSPath(subject=subject_id, session=session_id,
                 extension=extension)

    # do not error check extension in update (not deep check)
    bids_basename.update(extension='.foo')

    # test repr
    bids_path = BIDSPath(subject='01', session='02',
                         task='03', suffix='ieeg',
                         extension='.edf')
    assert repr(bids_path) == ('BIDSPath(\n'
                               'root: None\n'
                               'basename: sub-01_ses-02_task-03_ieeg.edf)')


def test_make_filenames():
    """Test that we create filenames according to the BIDS spec."""
    # All keys work
    prefix_data = dict(subject='one', session='two', task='three',
                       acquisition='four', run='five', processing='six',
                       recording='seven', suffix='ieeg', extension='.json')
    expected_str = 'sub-one_ses-two_task-three_acq-four_run-five_proc-six_rec-seven_ieeg.json'  # noqa
    assert BIDSPath(**prefix_data).basename == expected_str
    assert BIDSPath(**prefix_data) == op.join('sub-one', 'ses-two',
                                              'ieeg', expected_str)

    # subsets of keys works
    assert (BIDSPath(subject='one', task='three', run=4).basename ==
            'sub-one_task-three_run-04')
    assert (BIDSPath(subject='one', task='three',
                     suffix='meg', extension='.json').basename ==
            'sub-one_task-three_meg.json')

    with pytest.raises(ValueError):
        BIDSPath(subject='one-two', suffix='ieeg', extension='.edf')

    with pytest.raises(ValueError, match='At least one'):
        BIDSPath()

    # emptyroom check: invalid task
    with pytest.raises(ValueError, match='task must be'):
        BIDSPath(subject='emptyroom', session='20131201',
                 task='blah', suffix='meg')

    # when the suffix is not 'meg', then it does not result in
    # an error
    BIDSPath(subject='emptyroom', session='20131201',
             task='blah')

    # test what would happen if you don't want to check
    prefix_data['extension'] = '.h5'
    with pytest.raises(ValueError, match='Extension .h5 is not allowed'):
        BIDSPath(**prefix_data)
    basename = BIDSPath(**prefix_data, check=False)
    assert basename.basename == 'sub-one_ses-two_task-three_acq-four_run-five_proc-six_rec-seven_ieeg.h5'  # noqa

    # what happens with scans.tsv file
    with pytest.raises(ValueError, match='scans.tsv file name '
                                         'can only contain'):
        BIDSPath(
            subject=subject_id, session=session_id, task=task,
            suffix='scans', extension='.tsv'
        )


@pytest.mark.parametrize(
    'entities, expected_n_matches',
    [
        (dict(), 9),
        (dict(subject='01'), 2),
        (dict(task='audio'), 2),
        (dict(processing='sss'), 1),
        (dict(suffix='meg'), 4),
        (dict(acquisition='lowres'), 1),
        (dict(task='test', processing='ica', suffix='eeg'), 2),
        (dict(subject='5', task='test', processing='ica', suffix='eeg'), 1)
    ])
def test_filter_fnames(entities, expected_n_matches):
    """Test filtering filenames based on BIDS entities works."""

    fnames = ('sub-01_task-audio_meg.fif',
              'sub-01_ses-05_task-audio_meg.fif',
              'sub-02_task-visual_eeg.vhdr',
              'sub-Foo_ses-bar_meg.fif',
              'sub-Bar_task-invasive_run-1_ieeg.fif',
              'sub-3_task-fun_proc-sss_meg.fif',
              'sub-4_task-pain_acq-lowres_T1w.nii.gz',
              'sub-5_task-test_proc-ica_eeg.vhdr',
              'sub-6_task-test_proc-ica_eeg.vhdr')

    output = _filter_fnames(fnames, **entities)
    assert len(output) == expected_n_matches


def test_get_matched_basenames(return_bids_test_dir):
    """Test retrieval of matching basenames."""
    bids_root = return_bids_test_dir

    paths = get_matched_basenames(bids_root=bids_root)
    assert len(paths) == 7
    assert all('sub-01_ses-01' in p.basename for p in paths)
    assert all([p.root == bids_root for p in paths])

    paths = get_matched_basenames(bids_root=bids_root, run='01')
    assert len(paths) == 3
    assert paths[0].basename == 'sub-01_ses-01_task-testing_run-01_channels'

    paths = get_matched_basenames(bids_root=bids_root, subject='unknown')
    assert len(paths) == 0