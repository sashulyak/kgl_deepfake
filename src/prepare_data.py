import os
import json
from multiprocessing import Pool, set_start_method
from typing import List, Tuple, Union

import cv2
import numpy as np
import torch
from sklearn.model_selection import GroupShuffleSplit
from tqdm import tqdm
from facenet_pytorch import MTCNN

import config
from utils import read_faces_from_video


try:
    set_start_method('spawn')
except RuntimeError:
    pass


device = 'cuda' if torch.cuda.is_available() else 'cpu'
detector = MTCNN(
    margin=14,
    factor=0.6,
    keep_all=True,
    device=device)


def get_train_data_lists(train_videos_dir: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Collect video paths and labels across all training groups.

    :param train_videos_dir: path to train data directory
    :return: list of train video paths, video file names, corresponding labels and groups (names of folders)
    """
    chunks_list = os.listdir(train_videos_dir)

    paths = []
    labels = []
    groups = []
    names = []
    for chunk_dir_name in chunks_list:
        chunk_dir = os.path.join(train_videos_dir, chunk_dir_name)
        chunk_file_names = os.listdir(chunk_dir)
        chunk_file_names = [name for name in chunk_file_names if name != 'metadata.json']

        metadata_file_path = os.path.join(chunk_dir, 'metadata.json')
        with open(metadata_file_path) as json_file:
            chunk_metadata = json.load(json_file)

        for video_file_name in chunk_file_names:
            paths.append(os.path.join(chunk_dir, video_file_name))
            labels.append(chunk_metadata[video_file_name]['label'] == 'FAKE')
            groups.append(chunk_dir_name)
            names.append(video_file_name)

    return np.array(paths), np.array(names), np.array(labels), np.array(groups)


def get_image_name_from_video_name(video_name: str, frame_number: int = None) -> str:
    """
    Map video name to corresponding extracted face image file.

    :param video_name: source video file name
    :param frame_number: frame number from which face was extracted
    :return: face image file name
    """
    if frame_number is not None:
        if frame_number > 99:
            template = '_{}.png'
        elif 9 < frame_number < 100:
            template = '_0{}.png'
        else:
            template = '_00{}.png'
        return video_name[:-4] + template.format(frame_number)
    else:
        return video_name[:-4] + '.png'


def save_faces_from_video(video_path: str) -> Union[str, Tuple]:
    """
    Extract faces from video and save each face to separate image file.

    :param video_path: path to source video
    :return: in case of success return face images paths, source video path and group (train subfolder name)
    in case of error return only path to source video
    """
    video_name = os.path.basename(video_path)
    face_paths = []
    group = video_path.split('/')[-2]
    for i in range(config.FRAMES_PER_VIDEO):
        image_name = get_image_name_from_video_name(video_name, i)
        face_paths.append(os.path.join(config.TRAIN_FACES_DIR, image_name))

    all_exists = True
    for image_path in face_paths:
        if not os.path.exists(image_path):
            all_exists = False
            break
    if all_exists:
        return face_paths, video_path, group

    try:
        faces_to_save = read_faces_from_video(video_path, detector, swap_channels=False)
    except Exception:
        return video_path

    for image_path, face in zip(face_paths, faces_to_save):
        try:
            cv2.imwrite(image_path, face)
        except Exception:
            return video_path
    return face_paths, video_path, group


def extract_faces_from_videos_parallel(paths: List[str]) -> np.ndarray:
    """
    Take each video from list, detect faces, and save face crops as separate images.

    :param paths: video paths
    :return: list of metadata dictionaries
    """
    os.makedirs(config.TRAIN_FACES_DIR, exist_ok=True)
    faces_metadata = []
    broken_videos = []

    with Pool(9) as p:
        with tqdm(total=len(paths)) as pbar:
            for i, saving_result in enumerate(p.imap_unordered(save_faces_from_video, paths)):
                if type(saving_result) is tuple:
                    faces_metadata.append({
                        'faces': saving_result[0],
                        'video': os.path.basename(saving_result[1]),
                        'group': saving_result[2]
                    })
                else:
                    broken_videos.append(saving_result)
                pbar.update()

    print('{} broken files out of {}'.format(len(broken_videos), len(paths)))

    with open(config.BROKEN_VIDEOS_PATH, 'w') as outfile:
        json.dump(broken_videos, outfile)

    return np.array(faces_metadata)


def save_faces_metadata_to_json(labels: np.ndarray, faces: np.ndarray, metadata_path: str) -> None:
    """
    Save all faces metadata to one json file.

    :param labels: video labels
    :param faces: corresponding faces metadata
    :param metadata_path: path to metadata file
    """
    faces_metadata = {}
    for label, faces_batch in zip(labels, faces):
        for face_path in faces_batch['faces']:
            faces_metadata[os.path.basename(face_path)] = {
                'label': int(label),
                'group': faces_batch['group'],
                'video': faces_batch['video']
            }

    with open(metadata_path, 'w') as outfile:
        json.dump(faces_metadata, outfile)


if __name__ == '__main__':
    np.random.seed(config.SEED)
    video_paths, video_file_names, labels, groups = get_train_data_lists(config.TRAIN_VIDEOS_DIR)

    video_paths, video_file_names, labels, groups = video_paths, video_file_names, labels, groups

    print('Total videos:', video_paths.shape)

    print('Extracting faces from videos ...')
    faces = extract_faces_from_videos_parallel(video_paths)

    print('Splitting data on train and validation ...')
    faces_groups = [face['group'] for face in faces]
    faces_videos = [face['video'] for face in faces]
    videos_labels_dict = dict(zip(video_file_names, labels))
    faces_labels = np.array([videos_labels_dict[video] for video in faces_videos])
    gss = GroupShuffleSplit(n_splits=1, train_size=0.8, random_state=config.SEED)
    train_idx, val_idx = next(gss.split(faces, faces_labels, faces_groups))
    print('Train len:', len(train_idx), ', Val len:', len(val_idx))

    print('Saving faces metadata ...')
    save_faces_metadata_to_json(
        faces_labels[train_idx],
        faces[train_idx],
        config.FACES_TRAIN_METADATA_PATH)
    save_faces_metadata_to_json(
        faces_labels[val_idx],
        faces[val_idx],
        config.FACES_VAL_METADATA_PATH)

    print('All done!')
