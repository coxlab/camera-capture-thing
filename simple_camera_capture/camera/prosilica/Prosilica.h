/*
 *  ProsilicaCamera.h
 *  EyeTrackerStageDriver
 *
 *  Created by David Cox on 6/18/08.
 *  Copyright 2008 __MyCompanyName__. All rights reserved.
 *
 */

#ifndef _PROSILICA_H
#define _PROSILICA_H

#include <deque>
#include <vector>
#include "PvApi.h"
#include <iostream>
#include <pthread.h>
#include <unistd.h>

//#include <opencv/cv.h>

//#include <cv.h>

#define FRAME_MULTI_BUFFER_SIZE 5
#define LOW_WATER_MARK 3

#define FRAME_PENDING   0
#define FRAME_READY     1
#define FRAME_LOCKED    2
#define FRAME_DONE      3


#define FRAME_CONTEXT_CAMERA 0
#define FRAME_CONTEXT_INDEX 1


using namespace std;



void frame_callback(tPvFrame *frame);

class ProsilicaCamera {
    
protected:
    
    static bool prosilica_initialized;
    
    tPvHandle camera_handle;
    
    // For single frame acquisition
    tPvFrame frame;
    
    // For continuous acquisition
    tPvFrame frame_multi_buffer[FRAME_MULTI_BUFFER_SIZE];
    tPvFrame *current_frame;
        
    deque<tPvFrame *> ready_frames;
    pthread_mutex_t ready_frames_lock;
       
    pthread_cond_t  frame_ready_cond;
    
    int nqueued;
    
public:
    
	ProsilicaCamera(tPvCameraInfo info): ready_frames(){
	    
        _check(PvCameraOpen(info.UniqueId,  ePvAccessMaster, &camera_handle));
    
        // initialize a frame for a single-frame acquistion
        _initFrame(&frame, -1);
        
        nqueued = 0;

        // initialize frames for buffered acquisition
        for(int i = 0; i < FRAME_MULTI_BUFFER_SIZE; i++){
            _initFrame(&(frame_multi_buffer[i]), i);
        }
        pthread_mutex_init (&ready_frames_lock, NULL);
        pthread_cond_init(&frame_ready_cond, NULL);   

        current_frame = &frame;     
	}
    

    // Set a camera attribute (e.g. 'binningX')
    void setAttribute(const char *attr_name, unsigned int value){
        PvAttrUint32Set(camera_handle, attr_name, (tPvUint32)value);
    }
        
    void setAttribute(const char *attr_name, float value){
        PvAttrFloat32Set(camera_handle, attr_name, (tPvFloat32)value);
    }
    
    // Get camera parameters by name
    unsigned int getUint32Attribute(const char *attr_name){
        tPvUint32 val;
        PvAttrUint32Get(camera_handle, attr_name, &val);
        return  (unsigned int)val;
    }
    
    float getFloat32Attribute(const char *attr_name){
        tPvFloat32 val;
        PvAttrFloat32Get(camera_handle, attr_name, &val);
        return  (float)val;
    }    


    // Allocate memory for one image frame    
    void _initFrame(tPvFrame *frame, int index){
        tPvUint32 FrameSize = 0;
        FrameSize = 659*493;
        //_check(PvAttrUint32Get(camera_handle,"TotalBytesPerFrame",&FrameSize));

        cerr << "FrameSize = " << FrameSize << endl;
        
        frame->ImageBuffer = new char[FrameSize];
        if(frame->ImageBuffer){
            frame->ImageBufferSize = FrameSize;
        } else {
		    cerr << "Failed to allocate memory for frame buffer" << endl;
            return;
        }
        frame->Context[FRAME_CONTEXT_CAMERA] = (void *)this;
        int *frame_index = (int *)calloc(1, sizeof(int));
        *frame_index = index;
        frame->Context[FRAME_CONTEXT_INDEX] = frame_index;
        
    }
		

    // Error checking
	tPvErr _check(tPvErr result){
		//cerr << "checking..." << endl;
		_reportError(result);
		return result;
	}
		
	void _reportError(tPvErr result){
		if(result != ePvErrSuccess){
			switch(result){
				case ePvErrCameraFault:
					cerr << "Unexpected camera fault" << endl;
					break;
				case ePvErrInternalFault:
					cerr << "Internal Fault" << endl;
					break;
				case ePvErrBadHandle:
					cerr << "Bad handle" << endl;
					break;
				case ePvErrBadParameter:
					cerr << "Bad parameter" << endl;
					break;
				case ePvErrBadSequence:
                    //cerr << "Bad sequence" << endl;
					break;
				case ePvErrNotFound:
					cerr << "Not found" << endl;
					break;
				case ePvErrAccessDenied:
					cerr << "Access denied" << endl;
					break;
				case ePvErrUnplugged:
					cerr << "Unplugged" << endl;
					break;
				case ePvErrInvalidSetup:
					cerr << "Invalid setup" << endl;
					break;
				case ePvErrResources:
					cerr << "Resources unavailable" << endl;
					break;
				case ePvErrQueueFull:
					cerr << "Queue full" << endl;
					break;
				case ePvErrBufferTooSmall:
					cerr << "Buffer too small" << endl;
					break;
				case ePvErrCancelled:
					cerr << "Frame cancelled" << endl;
					break;
				case ePvErrDataLost:
					cerr << "Data lost" << endl;
					break;
				case ePvErrDataMissing:
					cerr << "Data missing" << endl;
					break;
				case ePvErrTimeout:
					cerr << "Timeout" << endl;
					break;
				case ePvErrOutOfRange:
					cerr << "Out of range" << endl;
					break;
				case ePvErrWrongType:
					cerr << "Wrong type" << endl;
					break;
				case ePvErrForbidden:
					cerr << "Attribute is Forbidden" << endl;
					break;
				case ePvErrUnavailable:
					cerr << "attribute is unavailable" << endl;
					break;
				//case ePvErrFirewall:
//					cerr << "A firewall is preventing proper function" << endl;
//					break;	
				default:
					cerr << "Unknown error" << endl;
			}
		} else {
				//cerr << "All's well" << endl;
		}
	}
    	
	
    ProsilicaCamera(unsigned long camera_id){
        PvCameraOpen(camera_id,  ePvAccessMaster, &camera_handle);
    }
    
    ~ProsilicaCamera(){
        cerr << "Deleting camera" << endl;
		if(isCapturing()){
            endCapture();
        }
        PvCameraClose(camera_handle);
    }
    
    
    // Capture methods for single frames
    bool startCapture(){
 
        // set the camera is capture mode
        if(!(_check(PvCaptureStart(camera_handle)))){
            // set the camera in continuous acquisition mode
            if(!_check(PvAttrEnumSet(camera_handle,"FrameStartTriggerMode","Freerun"))){			
                    
                if(_check(PvCommandRun(camera_handle, "AcquisitionStart"))){
                    // if that fail, we reset the camera to non capture mode
                    cerr << "Failed acquisition start" << endl;
                    _check(PvCaptureEnd(camera_handle)) ;
                    return false;
                } else {
                    return true;
                }
        
            } else {
                cerr << "Failed FrameStartTriggerMode set" << endl;
            }
        } else {
            cerr << "Failed CaptureStart" << endl;
        }
        
        return false;
    }
    
    bool endCapture(){
        _check(PvCommandRun(camera_handle,"AcquisitionStop"));
        _check(PvCaptureEnd(camera_handle));
		return true;
    }    
    

    bool isCapturing(){
        unsigned long is_started;
        _check(PvCaptureQuery(camera_handle, &is_started));
        
        return is_started;
    }
    
    
    // Synchronization

    void lockReadyFrames(){
       pthread_mutex_lock(&ready_frames_lock);
    }
        
    void unlockReadyFrames(){
       pthread_mutex_unlock(&ready_frames_lock); 
    }
        
    void waitForReadyFrames(){
        pthread_cond_wait(&frame_ready_cond, &ready_frames_lock);
    }
    
    void broadcastFrameReady(){
        cerr << "FRAME READY" << endl;
        pthread_cond_broadcast(&frame_ready_cond);
    }
        
        
    // Lock ready_frames and return one frame (e.g. so it can be copied)
    tPvFrame getAndLockCurrentFrame(){

        lockReadyFrames();
        cerr << "Ready: " << ready_frames.size() << " / Queued: " << nqueued << endl;
        while(ready_frames.size() == 0){
            waitForReadyFrames();
            // unlockReadyFrames();
            // return frame; // return empty dummy frame
        // //     //cerr << "\tgot one" << endl;
        // //     tPvFrame empty;
        // //     return empty;
        }
        
        current_frame = ready_frames.front();
        ready_frames.pop_front();
        unlockReadyFrames();

        return *current_frame;
    }

    // Tell PvAPI that it can put data into a particular frame struct
    void queueCameraFrame(int frame_index){     
        // cerr << "here" << endl;

        _check(PvCaptureQueueFrame(camera_handle,&frame_multi_buffer[frame_index], &frame_callback));
        nqueued++;

        // cerr << "queueing: " << nqueued << endl;
    }

    
    // let go of the frame and requeue it
    void releaseCurrentFrame(){
        int index = *((int *)current_frame->Context[FRAME_CONTEXT_INDEX]);
        
        if(index){
            queueCameraFrame(index);
            cerr << "released: " << index << endl;
        }
    }
    
    
    // Capture continuously
    // 1. Set frame triggering and call 
    bool startContinuousCapture(){
        cerr << "Starting continuous capture..." << endl;


        // call PvCaptureStart to begin specifying parameters
        if(!(_check(PvCaptureStart(camera_handle)))){
            // set the camera in continuous acquisition mode
            if(!_check(PvAttrEnumSet(camera_handle,"FrameStartTriggerMode","Freerun"))){			
                // and set the acquisition mode into continuous
                //return true;
            } else {
                cerr << "Failed FrameStartTriggerMode set" << endl;
            }
        } else {
            cerr << "Failed CaptureStart" << endl;
        }
        
        // Queue up a bunch of frames
        for(int i=0; i < FRAME_MULTI_BUFFER_SIZE; i++){
            // cerr << "Queueing tPvFrame index " << i << endl;
            queueCameraFrame(i);
        }
        

        // AcquisitionStart actually gets things moving
        if(_check(PvCommandRun(camera_handle,"AcquisitionStart"))){
            // if that fail, we reset the camera to non capture mode
            cerr << "Failed acquisition start" << endl;
            _check(PvCaptureEnd(camera_handle)) ;
            return false;
        } else {
            return true;
        }
    }
        
    // A callback for when PvAPI has filled a particular frame.
    // When this happens, we should put it on the ready pile.
    // if we're getting close to the edge (HIGH_WATER_MARK), then
    // grab a frame off of the ready pile and queue it up
    void frameCompleted(tPvFrame *frame){

        int frame_index = *((int *)frame->Context[FRAME_CONTEXT_INDEX]);
        //int frame_index = 4;

        tPvFrame *requeue_frame = NULL;

        // cerr << "nqueued: " << nqueued << endl;
        // cerr << "filling frame: " << frame_index << endl;

        cerr.flush();
 

        lockReadyFrames();
        
        // put the completed frame in ready_frames
        ready_frames.push_back(&frame_multi_buffer[frame_index]);

        nqueued--;


        // if there are not enough frames currently queued
        while(nqueued < LOW_WATER_MARK){
            // take one off of the front and requeue it
            requeue_frame = ready_frames.front();
            ready_frames.pop_front();

            int requeue_frame_index = *((int *)requeue_frame->Context[FRAME_CONTEXT_INDEX]);
            
            cerr << "DROPPED FRAME: requeued frame index: " << requeue_frame_index << endl;
            queueCameraFrame(requeue_frame_index);
        }

        unlockReadyFrames();

        broadcastFrameReady();
    }
        
//     tPvFrame captureOnePvFrame(){
//         if(!_check(PvCaptureQueueFrame(camera_handle,&frame,NULL))){
            
// 			//printf("waiting for the frame to be done ...\n");
//             while(_check(PvCaptureWaitForFrameDone(camera_handle,&frame,100)) == ePvErrTimeout){
//                 printf("still waiting ...\n");
//             }
//             if(frame.Status == ePvErrSuccess){
            
//                 return frame;
// //                if(!ImageWriteTiff("./snap.tiff",&(Camera->Frame))){
// //                    printf("Failed to save the grabbed frame!");
// //                } else {
// //                    printf("frame saved\n");
// //                }
//             } else {
//                 printf("the frame failed to be captured ...\n");
//             }
//         } else {
//             printf("failed to enqueue the frame\n");
//         }
//     }
    
    
    // ---------------
    // static methods
    // ---------------

    static void initialize(){
        if(!PvInitialize()){
            ProsilicaCamera::prosilica_initialized = true;
        }
    }

    static int getNumberOfCameras(){
        return PvCameraCount();
    }
};





// Helper function (for bridging to python)
// should be called with dim = width * height
// (maybe move this out as an %extend?
void _frameTo1DArray(tPvFrame frame, short *array, int dim);
std::vector<tPvCameraInfo> getCameraList();
void test_it(short *array, int dim);
tPvFrame *test_it2();



#endif

