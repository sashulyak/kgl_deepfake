from typing import List, Tuple

import cv2
import numpy as np
from facenet_pytorch import MTCNN

import config


def extend_rect_to_square(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    image_width: int,
    image_height: int
) -> Tuple[int, int, int, int]:
    """
    Extend bounding box rectangle to the nearest square.

    :param start_x: left rectangle coordinate
    :param start_y: top rectange coordinate
    :param end_x: righ rectange coordinate
    :param end_y: bottom rectange coordinate
    :param image_width: source image width
    :param image_height: source image height
    :return: square coordinates
    """
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


def read_faces_from_video(path: str, detector: MTCNN, img_size=None, swap_channels=True) -> List[np.ndarray]:
    """
    Open video file, detect faces in it, crop and return.

    :param path: path to source video
    :param detector: face detector model
    :param img_size: face target size
    :param swap_channels: if True, swap bluee and red channels
    :return: list of cropped faces
    """
    capture = cv2.VideoCapture(path)
    num_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    faces_to_save = []
    for i in range(0, num_frames):
        ret = capture.grab()
        if i % 10 == 0:
            ret, frame = capture.retrieve()
            faces_groups, confidences_groups = detector.detect([cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)])
            faces = faces_groups[0]
            confidences = confidences_groups[0]
            if len(confidences) > 0:
                most_confident_face_index = np.argmax(confidences)
                (start_x, start_y, end_x, end_y) = faces[most_confident_face_index]
                (start_x, start_y, end_x, end_y) = (int(start_x), int(start_y), int(end_x), int(end_y))
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
    assert len(faces_to_save) == config.FRAMES_PER_VIDEO
    return faces_to_save
