import os
from multiprocessing import Pool
from typing import List

import cv2
import cvlib as cv
import numpy as np
from tqdm import tqdm

import config


def extend_rect_to_square(start_x, start_y, end_x, end_y, image_width, image_height):
    width = end_x - start_x
    height = end_y - start_y
    if width > height:
        difference = width - height
        start_y -= difference // 2
        end_y += difference // 2
    else:
        difference = height - width
        start_x -= difference // 2
        end_x += difference // 2
    start_x_result = np.max([0, start_x])
    start_y_result = np.max([0, start_y])
    end_x_result = np.min([image_width, end_x])
    end_y_result = np.min([image_height, end_y])

    return start_x_result, start_y_result, end_x_result, end_y_result


def read_faces_from_video(path: str, img_size=None, swap_channels=True) -> List[str]:
    capture = cv2.VideoCapture(path)
    num_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    faces_to_save = []
    for i in range(0, num_frames):
        ret = capture.grab()
        if i % 10 == 0:
            ret, frame = capture.retrieve()
            faces, confidences = cv.detect_face(frame)
            if len(confidences) > 0:
                most_confident_face_index = np.argmax(confidences)
                (start_x, start_y, end_x, end_y) = faces[most_confident_face_index]
                (start_x, start_y, end_x, end_y) = extend_rect_to_square(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    frame.shape[1],
                    frame.shape[0])
                face_crop = frame[start_y:end_y, start_x:end_x]
                if face_crop.shape[0] > 0 and face_crop.shape[1] > 0:
                    if swap_channels:
                        face_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                    if img_size:
                        face_crop = cv2.resize(face_crop, (img_size, img_size))
                    faces_to_save.append(face_crop)
            if len(faces_to_save) == config.FRAMES_PER_VIDEO:
                break
    capture.release()
    assert len(faces_to_save) > 0
    return faces_to_save


def is_file_corrupted(file_path):
    try:
        read_faces_from_video(file_path)
        return False
    except Exception:
        return True


def get_corrupted_file_indexes(video_file_names, videos_directory, video_groups=None, verbose=False):
    if video_groups is not None:
        group_paths = [os.path.join(videos_directory, group) for group in video_groups]
        video_file_paths = []
        for group_path, filename in zip(group_paths, video_file_names):
            video_file_paths.append(os.path.join(group_path, filename))
    else:
        video_file_paths = [os.path.join(videos_directory, filename) for filename in video_file_names]

    if verbose:
        corrupted_files_indexes = list(tqdm(
            Pool().imap(is_file_corrupted, video_file_paths),
            total=len(video_file_paths)))
    else:
        corrupted_files_indexes = Pool().map(is_file_corrupted, video_file_paths)
    return np.array(corrupted_files_indexes)