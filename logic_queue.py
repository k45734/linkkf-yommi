# -*- coding: utf-8 -*-
#########################################################
# python
import os,re
import traceback
import sys
import logging
import threading
import queue
import platform
import subprocess

# import Queue
# from .logic_queue import LogicQueue
import json
import time
from datetime import datetime
import requests

# third-party
import yt_dlp # <<<<<<<<<<<<<<< yt-dlp 임포트 추가

# sjva 공용
from framework import db, scheduler, path_data
from framework.job import Job
from framework.util import Util
from framework.logger import get_logger

# 패키지
# from .plugin import package_name, logger
import system
from .model import ModelSetting, ModelLinkkf

# from plugin import LogicModuleBase, FfmpegQueueEntity, FfmpegQueue, default_route_socketio

# from .tool import WVTool

#########################################################
package_name = __name__.split(".")[0]
logger = get_logger(package_name)

# sys.stdout.write(QueueEntity.get_entity_by_entity_id([]))


class QueueEntity:
# ... (중략: QueueEntity 클래스 내용 유지) ...
    static_index = 1
    entity_list = []

    def __init__(self, info):
        # logger.info('info:::::>> %s', info)
        self.entity_id = info["code"]
        self.info = info
        self.url = None
        self.ffmpeg_status = -1
        self.ffmpeg_status_kor = "대기중"
        self.ffmpeg_percent = 0
        self.ffmpeg_arg = None
        self.cancel = False
        self.created_time = datetime.now().strftime("%m-%d %H:%M:%S")
        self.status = None
        QueueEntity.static_index += 1
        QueueEntity.entity_list.append(self)

    @staticmethod
    def create(info):
        for e in QueueEntity.entity_list:
            if e.info["code"] == info["code"]:
                return
        ret = QueueEntity(info)
        return ret

    @staticmethod
    def get_entity_by_entity_id(entity_id):
        ret_data = []
        # logger.debug(type(QueueEntity.entity_list))
        for _ in QueueEntity.entity_list:
            # logger.debug(type(_))
            if _.entity_id == entity_id:
                ret_data.append(_)
                return _
        # for _ in QueueEntity.entity_list:
        #     if _.entity_id == entity_id:

        # return None


class LogicQueue(object):
    download_queue = None
    download_thread = None
    current_ffmpeg_count = 0

    def refresh_status(self):
        self.module_logic.socketio_callback("status", self.as_dict())

    @staticmethod
    def queue_start():
        try:
            if LogicQueue.download_queue is None:
                LogicQueue.download_queue = queue.Queue()
            # LogicQueue.download_queue = Queue.Queue()
            if LogicQueue.download_thread is None:
                LogicQueue.download_thread = threading.Thread(
                    target=LogicQueue.download_thread_function, args=()
                )
                LogicQueue.download_thread.daemon = True
                LogicQueue.download_thread.start()
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    @staticmethod
    def download_thread_function():
        # ... (중략) ...
        # yt-dlp 다운로드 로직 삽입
        try:
            # yt-dlp 옵션 설정
            outtmpl = os.path.join(save_path, entity.info["filename"])
            
            # ... (yt_dlp 옵션 설정 유지) ...

            LogicQueue.current_ffmpeg_count += 1
            
            entity.ffmpeg_status_kor = "다운로드중"
            entity.ffmpeg_status = 5
            plugin.socketio_list_refresh()
            
            # --- 다운로드 실행 ---
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # ydl.download()는 파일 이름 자체를 반환하지 않으므로, extract_info를 사용합니다.
                # 단순 다운로드만 원할 경우 download()를 사용하지만, 파일 경로 검증을 위해 
                # 여기서는 download()를 사용하고 outtmpl을 기준으로 검사합니다.
                ydl.download([entity.url[0]])

            # --- 파일 존재 여부 최종 검증 로직 추가 ---
            
            # 최종 파일 경로 (outtmpl에서 확장자나 타이틀 변수가 사용되지 않은 단순 경로라고 가정)
            final_filepath = outtmpl
            
            # 만약 outtmpl에 %(title)s.%(ext)s와 같은 변수가 포함되어 있다면, 
            # yt-dlp의 info_dict를 가져와서 실제 파일명을 파악해야 합니다. 
            # 단순화를 위해 여기서는 outtmpl 경로에 파일이 생성되었다고 가정하고 파일 존재 여부만 체크합니다.
            
            is_file_exist = os.path.exists(final_filepath)
            
            if is_file_exist and os.path.getsize(final_filepath) > 0:
                # ------------------- 성공 로직 -------------------
                LogicQueue.current_ffmpeg_count -= 1 
                
                # DB 업데이트 로직 (COMPLETED)
                episode = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
                if episode:
                    episode.completed = True
                    episode.end_time = datetime.now()
                    episode.completed_time = episode.end_time
                    episode.filename = entity.info["filename"]
                    episode.status = "completed"
                    db.session.commit()
                
                entity.ffmpeg_status_kor = "완료"
                entity.ffmpeg_status = 7
                entity.ffmpeg_percent = 100
                plugin.socketio_list_refresh()

            else:
                # ------------------- 실패 로직 (파일이 없거나 크기가 0) -------------------
                logger.error(f"yt-dlp 다운로드는 예외없이 종료되었으나, 파일이 생성되지 않거나 크기가 0입니다: {final_filepath}")
                
                LogicQueue.current_ffmpeg_count -= 1 
                
                # DB 업데이트 로직 (ERROR)
                episode = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
                if episode:
                    episode.etc_abort = 1 # ERROR
                    db.session.commit()
                    
                entity.ffmpeg_status_kor = "다운로드 실패 (파일 없음)"
                entity.ffmpeg_status = 6
                plugin.socketio_list_refresh()
            
        except yt_dlp.DownloadError as e:
            logger.error(f"yt-dlp Download Error: {e}")
            # ... (기존 실패 로직 유지) ...
            if LogicQueue.current_ffmpeg_count > 0:
                LogicQueue.current_ffmpeg_count -= 1 
            
            episode = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
            if episode:
                episode.etc_abort = 1
                db.session.commit()
                
            entity.ffmpeg_status_kor = "다운로드 실패"
            entity.ffmpeg_status = 6
            plugin.socketio_list_refresh()

        except Exception as e:
            logger.error("yt-dlp 일반 Exception:%s", e)
            logger.error(traceback.format_exc())
            # ... (기존 일반 예외 로직 유지) ...
            if LogicQueue.current_ffmpeg_count > 0:
                LogicQueue.current_ffmpeg_count -= 1 

        finally:
            # 성공/실패 여부에 관계없이 큐 작업 완료 처리
            LogicQueue.download_queue.task_done()

    @staticmethod
    def download_thread_function():
        headers = None
        from . import plugin

        # import plugin
        while True:
            try:
                while True:
                    if LogicQueue.current_ffmpeg_count < int(
                        ModelSetting.get("max_ffmpeg_process_count")
                    ):
                        break
                    # logger.debug(LogicQueue.current_ffmpeg_count)
                    time.sleep(5)
                entity = LogicQueue.download_queue.get()

                # Todo: 고찰
                # if entity.cancel:
                #     continue

                # logger.debug(
                #     "download_thread_function()::entity.info['code'] >> %s", entity
                # )

                if entity is None:
                    continue

                # db에 해당 에피소드가 존재하는 확인
                db_entity = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
                if db_entity is None:
                    episode = ModelLinkkf("auto", info=entity.info)
                    db.session.add(episode)
                    db.session.commit()
                else:
                    # episode = ModelLinkkf("auto", info=entity.info)
                    # query = db.session.query(ModelLinkkf).filter_by(episodecode=entity.info.episodecode).with_for_update().first()
                    pass

                from .logic_linkkfyommi import LogicLinkkfYommi

                # entity.url = LogicLinkkfYommi.get_video_url(
                #     entity.info['code'])
                logger.debug(f"entity.info[url] = {entity.info['url']}")
                entity.url = LogicLinkkfYommi.get_video_url(entity.info["url"])

                logger.info("entity.info: %s", entity.info["url"])
                logger.debug(f"entity.url: {entity.url}")
                # logger.info('url1: %s', entity.url[0])
                # print(entity)
                # logger.info('entity: %s', entity.__dict__)

                # logger.info('entity.url:::> %s', entity.url)
                if entity.url[0] is None:
                    LogicQueue.ffmpeg_status_kor = "URL실패"
                    plugin.socketio_list_refresh()
                    LogicQueue.download_queue.task_done() # URL 실패 시 큐 완료 처리
                    continue

                # import ffmpeg # <<<<<<<<<<<<<<<< FFmpeg 임포트 제거

                max_pf_count = 0
                referer = None
                save_path = ModelSetting.get("download_path")
                if ModelSetting.get("auto_make_folder") == "True":
                    program_path = os.path.join(save_path, entity.info["save_folder"])
                    save_path = program_path
                    if ModelSetting.get("linkkf_auto_make_season_folder"):
                        save_path = os.path.join(
                            save_path, "Season %s" % int(entity.info["season"])
                        )
                try:
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                except Exception as e:
                    logger.debug("program path make fail!!")

                if referer is None:
                    referer = "https://kfani.me/"

                # 파일 존재여부 체크
                if entity.url[1] is not None:
                    referer = entity.url[1]

                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36",
                        # 'Accept':
                        #     'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                        # 'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                        "Referer": f"{referer}",
                    }
                    # logger.info('referer: %s', referer)

                # logger.info('filename::::>>>> %s', entity.info['filename'])
                # logger.info('파일체크::::>', os.path.join(save_path, entity.info['filename']))
                if os.path.exists(os.path.join(save_path, entity.info["filename"])):
                    entity.ffmpeg_status_kor = "파일 있음"
                    entity.ffmpeg_percent = 100
                    plugin.socketio_list_refresh()
                    LogicQueue.download_queue.task_done() # <<<<<<<<<<<<<<<< 파일 존재 시 큐 완료 처리 추가
                    continue

                headers = {
                    # "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    # "Chrome/71.0.3554.0 Safari/537.36Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    # "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3554.0 Safari/537.36",
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36",
                    "Referer": f"{referer}",
                }
                # logger.debug(f"referer: {referer}")

                logger.debug(f"headers::: {headers}")

                if "nianv3c2.xyz" in entity.url[0]:
                    logger.debug(f"new type {entity.url[0]}")
                    #WVTool.aria2c_download(entity.url[0], "./temp") # aria2c 로직 유지
                    LogicQueue.download_queue.task_done() # <<<<<<<<<<<<<<<< aria2c 완료 시 큐 완료 처리
                else:
                    # target = save_path + '/' + entity.info["filename"]
                    # if not os.path.exists('{}'.format(save_path)):
                    #     os.makedirs('{}'.format(save_path))
                    # source = entity.url[0]
                    # headers_command = []
                    # for key, value in headers.items():
                    #     if key.lower() == 'user-agent':
                    #         headers_command.append('-user_agent')
                    #         headers_command.append(value)
                    #         pass
                    #     else:
                    #         headers_command.append('-headers')
                    #         if platform.system() == 'Windows':
                    #             headers_command.append('\'%s:%s\''%(key,value))
                    #         else:
                    #             headers_command.append(f'{key}:{value}')
                    # hh2 = ' '.join(headers_command)
                    # command = ['ffmpeg', '-y', hh2, '-i', source, '-c', 'copy', target]
                    # logger.info('%s',command)
                    # test = ' '.join(command)
                    # subprocess.call(test, universal_newlines=True, encoding='utf8') # <<<<<<<<<<<<<<<< FFmpeg 명령어 실행 주석 제거
                    # f = ffmpeg.Ffmpeg( # <<<<<<<<<<<<<<<< FFmpeg 객체 실행 제거
                    #     entity.url[0],
                    #     entity.info["filename"],
                    #     plugin_id=entity.entity_id,
                    #     listener=LogicQueue.ffmpeg_listener,
                    #     max_pf_count=max_pf_count,
                    #     #   referer=referer,
                    #     call_plugin=package_name,
                    #     save_path=save_path,
                    #     headers=headers,
                    # )
                    # f.start() # <<<<<<<<<<<<<<<< FFmpeg start 제거

                    # yt-dlp 다운로드 로직 삽입
                    try:
                        # yt-dlp 옵션 설정
                        outtmpl = os.path.join(save_path, entity.info["filename"])
                        
                        # yt-dlp는 기본적으로 최적 포맷을 선택하고 FFmpeg로 병합합니다.
                        ydl_opts = {
                            'outtmpl': outtmpl,
                            # 최적의 비디오와 오디오를 선택하고 병합하며, MP4로 변환 시도
                            # bestvideo[ext=mp4]+bestaudio[ext=m4a] 포맷을 사용하여 병합 시도
                            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 
                            'http_headers': headers,
                            'noplaylist': True, 
                            'no_warnings': True,
                            'ignoreerrors': False, # 오류를 무시하지 않고 예외 발생 유도
                            'abort_on_error': True, # 오류 발생 시 다운로드 중단
                            'quiet': True,
                        }
                        
                        # 프록시 설정 (ModelSetting에서 직접 가져옴)
                        if ModelSetting.get('use_proxy') == 'True':
                            ydl_opts['proxy'] = ModelSetting.get('proxy')

                        LogicQueue.current_ffmpeg_count += 1 # 다운로드 시작 전 카운트 증가
                        
                        # 상태 업데이트 (다운로드 시작)
                        entity.ffmpeg_status_kor = "다운로드중"
                        entity.ffmpeg_status = 5 # Ffmpeg.Status.DOWNLOADING (추정 값)
                        plugin.socketio_list_refresh()
                        
                        # 실제 yt-dlp 다운로드 (Blocking Call)
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([entity.url[0]])

                        # 다운로드 완료 후 상태 업데이트 및 DB 처리
                        LogicQueue.current_ffmpeg_count -= 1 # 카운트 감소
                        
                        # DB 업데이트 로직 (COMPLETED 로직 대체)
                        episode = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
                        if episode:
                            episode.completed = True
                            episode.end_time = datetime.now()
                            episode.completed_time = episode.end_time
                            episode.filename = entity.info["filename"] # 최종 파일명
                            episode.status = "completed"
                            db.session.commit()
                        
                        entity.ffmpeg_status_kor = "완료"
                        entity.ffmpeg_status = 7 # Ffmpeg.Status.COMPLETED (추정 값)
                        entity.ffmpeg_percent = 100
                        plugin.socketio_list_refresh() # 소켓io 갱신

                    except yt_dlp.DownloadError as e:
                        logger.error(f"yt-dlp Download Error: {e}")
                        # 실패 시 카운트 감소
                        if LogicQueue.current_ffmpeg_count > 0:
                            LogicQueue.current_ffmpeg_count -= 1 
                        
                        # DB 업데이트 로직 (ERROR 로직 대체)
                        episode = ModelLinkkf.get_by_linkkf_id(entity.info["code"])
                        if episode:
                            episode.etc_abort = 1 # ERROR
                            db.session.commit()
                            
                        entity.ffmpeg_status_kor = "다운로드 실패"
                        entity.ffmpeg_status = 6 # Ffmpeg.Status.ERROR (추정 값)
                        plugin.socketio_list_refresh()
                    except Exception as e:
                        logger.error("yt-dlp 일반 Exception:%s", e)
                        logger.error(traceback.format_exc())
                        # 일반 예외 처리 시에도 카운트 감소 필요
                        if LogicQueue.current_ffmpeg_count > 0:
                            LogicQueue.current_ffmpeg_count -= 1 

                    LogicQueue.download_queue.task_done() # <<<<<<<<<<<<<<<< yt-dlp 완료/실패 시 큐 완료 처리

                # LogicQueue.current_ffmpeg_count += 1 # <<<<<<<<<<<<<<<< FFmpeg 카운트 중복 처리 제거
                # LogicQueue.download_queue.task_done() # <<<<<<<<<<<<<<<< FFmpeg 큐 완료 중복 처리 제거

                # vtt file to srt file
                from framework.common.util import write_file, convert_vtt_to_srt
                from urllib import parse

                #ourls = parse.urlparse(entity.url[1])
                # print(ourls)
                # logger.info('ourls:::>', ourls)
                #base_url = f"{ourls.scheme}://{ourls.netloc}"
                # logger.info('base_url:::>', base_url)

                # Todo: 임시 커밋 로직 해결하면 다시 처리
                # if "linkkf.app" in base_url:
                #     base_url = f"{ourls.scheme}://kfani.me"

                # vtt_url = base_url + entity.url[2]
                # 임시
                #base_url = "https://kfani.me"
                #vtt_url = base_url + entity.url[2]
                ret = re.compile(r'(http(s)?:\/\/)([a-z0-9\w]+\.*)+[a-z0-9]{2,4}')
                base_url_vtt = ret.match(entity.url[1])
                if 'https' in entity.url[2]:
                    vtt_url = entity.url[2]
                else:
                    vtt_url = base_url_vtt[0] + entity.url[2]
                logger.info('%s',entity.url[2])
                logger.debug(f"srt:url => {vtt_url}")
                srt_filepath = os.path.join(
                    save_path, entity.info["filename"].replace(".mp4", ".ko.srt")
                )
                # logger.info('srt_filepath::: %s', srt_filepath)
                if entity.url[2] is not None and not os.path.exists(srt_filepath):
                    # vtt_data = requests.get(vtt_url, headers=headers).text
                    # srt_data = convert_vtt_to_srt(vtt_data)
                    # write_file(srt_data, srt_filepath)
                    res = requests.get(vtt_url, headers=headers)
                    vtt_data = res.text
                    vtt_status = res.status_code
                    if vtt_status == 200:
                        srt_data = convert_vtt_to_srt(vtt_data)
                        write_file(srt_data, srt_filepath)
                    else:
                        logger.debug("자막파일 받을수 없슴")

            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())

    @staticmethod
    def remove_png_byte(path, output_path):
        filename = path.name
        print(path.path)
        with open(path.path, "rb") as ifile:
            with open(f"{output_path}/{filename}", "wb") as ofile:
                ifile.read(8)
                prev = None
                while True:
                    chunk = ifile.read(4096)
                    if chunk:
                        if prev:
                            ofile.write(prev)
                        prev = chunk
                    else:
                        break
                if prev:
                    ofile.write(prev[:-1])

    @staticmethod
    def ffmpeg_listener(**arg):
        # logger.debug(arg)
        # logger.debug(arg["plugin_id"])
        import ffmpeg

        refresh_type = None
        if arg["type"] == "status_change":
            if arg["status"] == ffmpeg.Status.DOWNLOADING:
                episode = (
                    db.session.query(ModelLinkkf)
                    .filter_by(episodecode=arg["plugin_id"])
                    .with_for_update()
                    .first()
                )
                if episode:
                    episode.ffmpeg_status = int(arg["status"])
                    episode.duration = arg["data"]["duration"]
                    db.session.commit()
            elif arg["status"] == ffmpeg.Status.COMPLETED:
                pass
            elif arg["status"] == ffmpeg.Status.READY:
                pass
        elif arg["type"] == "last":
            LogicQueue.current_ffmpeg_count += -1
            episode = (
                db.session.query(ModelLinkkf)
                .filter_by(episodecode=arg["plugin_id"])
                .with_for_update()
                .first()
            )
            if (
                arg["status"] == ffmpeg.Status.WRONG_URL
                or arg["status"] == ffmpeg.Status.WRONG_DIRECTORY
                or arg["status"] == ffmpeg.Status.ERROR
                or arg["status"] == ffmpeg.Status.EXCEPTION
            ):
                episode.etc_abort = 1
            elif arg["status"] == ffmpeg.Status.USER_STOP:
                episode.user_abort = True
                logger.debug("Status.USER_STOP received..")
            if arg["status"] == ffmpeg.Status.COMPLETED:
                episode.completed = True
                episode.end_time = datetime.now()
                episode.download_time = (episode.end_time - episode.start_time).seconds
                episode.completed_time = episode.end_time
                episode.filesize = arg["data"]["filesize"]
                episode.filename = arg["data"]["filename"]
                episode.filesize_str = arg["data"]["filesize_str"]
                episode.download_speed = arg["data"]["download_speed"]
                episode.status = "completed"
                logger.debug("Status.COMPLETED received..")
            elif arg["status"] == ffmpeg.Status.TIME_OVER:
                episode.etc_abort = 2
            elif arg["status"] == ffmpeg.Status.PF_STOP:
                episode.pf = int(arg["data"]["current_pf_count"])
                episode.pf_abort = 1
            elif arg["status"] == ffmpeg.Status.FORCE_STOP:
                episode.etc_abort = 3
            elif arg["status"] == ffmpeg.Status.HTTP_FORBIDDEN:
                episode.etc_abort = 4
            db.session.commit()
            logger.debug("LAST commit %s", arg["status"])
        elif arg["type"] == "log":
            pass
        elif arg["type"] == "normal":
            pass
        if refresh_type is not None:
            pass

        entity = QueueEntity.get_entity_by_entity_id(arg["plugin_id"])
        if entity is None:
            return
        entity.ffmpeg_arg = arg
        entity.ffmpeg_status = int(arg["status"])
        entity.ffmpeg_status_kor = str(arg["status"])
        entity.ffmpeg_percent = arg["data"]["percent"]
        entity.status = int(arg["status"])
        from . import plugin

        arg["status"] = str(arg["status"])
        plugin.socketio_callback("status", arg)

    # @staticmethod
    # def add_queue(info):
    #     try:
    #         entity = QueueEntity.create(info)
    #         if entity is not None:
    #             LogicQueue.download_queue.put(entity)
    #             return True
    #     except Exception as e:
    #         logger.error("Exception:%s", e)
    #         logger.error(traceback.format_exc())
    #     return False
    @staticmethod
    def add_queue(info):
        try:

            # Todo:
            # if is_exist(info):
            #     return 'queue_exist'
            # logger.debug("add_queue()::info >> %s", info)
            # logger.debug("info::", info["_id"])

            # episode[] code (episode_code)
            db_entity = ModelLinkkf.get_by_linkkf_id(info["code"])
            # logger.debug("add_queue:: db_entity >> %s", db_entity)

            if db_entity is None:
                entity = QueueEntity.create(info)

                # logger.debug("add_queue()::entity >> %s", entity)
                LogicQueue.download_queue.put(entity)
                return "enqueue_db_append"
            elif db_entity.status != "completed":
                entity = QueueEntity.create(info)
                # return "Debugging"
                LogicQueue.download_queue.put(entity)

                logger.debug("add_queue()::enqueue_db_exist")
                return "enqueue_db_exist"
            else:
                return "db_completed"

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        return False

    @staticmethod
    def program_auto_command(req):
        logger.debug(f"program_auto_command routine ====================")
        try:
            from . import plugin

            logger.debug(req)

            command = req.form["command"]
            entity_id = int(req.form["entity_id"])
            logger.debug("command :%s %s", command, entity_id)
            entities = QueueEntity.get_entity_by_entity_id(entity_id)
            logger.debug("entity::> %s", entities)

            # logger.info('logic_queue:: entity', entity)

            ret = {}
            if command == "cancel":
                if entities.status == -1:
                    entities.cancel = True
                    entities.status_kor = "취소"
                    plugin.socketio_list_refresh()
                    ret["ret"] = "refresh"
                elif entities.status != 5:
                    ret["ret"] = "notify"
                    ret["log"] = "다운로드 중인 상태가 아닙니다."
                else:
                    idx = entities.ffmpeg_arg["data"]["idx"]
                    import ffmpeg

                    ffmpeg.Ffmpeg.stop_by_idx(idx)
                    plugin.socketio_list_refresh()
                    ret["ret"] = "refresh"
            elif command == "reset":
                if LogicQueue.download_queue is not None:
                    with LogicQueue.download_queue.mutex:
                        LogicQueue.download_queue.queue.clear()
                    for _ in QueueEntity.entity_list:
                        if _.ffmpeg_status == 5:
                            import ffmpeg

                            idx = _.ffmpeg_arg["data"]["idx"]
                            ffmpeg.Ffmpeg.stop_by_idx(idx)
                QueueEntity.entity_list = []
                plugin.socketio_list_refresh()
                ret["ret"] = "refresh"
            elif command == "delete_completed":
                new_list = []
                for _ in QueueEntity.entity_list:
                    if _.ffmpeg_status_kor in ["파일 있음", "취소"]:
                        continue
                    if _.ffmpeg_status != 7:
                        new_list.append(_)
                QueueEntity.entity_list = new_list
                plugin.socketio_list_refresh()
                ret["ret"] = "refresh"

        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            ret["ret"] = "notify"
            ret["log"] = str(e)
        return ret
