#! /usr/bin/env python
from __future__ import print_function
from __future__ import division

import sys
from collections import deque
import traceback

import numpy as np

import roslib
roslib.load_manifest('competition_2019t2')
import rospy
import cv2

from sensor_msgs.msg import Image

from cv_bridge import CvBridge, CvBridgeError

from plates import getPlates, PlateRect

class NoLicensePlatesException(Exception):
    pass

class PlateReader:

    def __init__(self):
        self.bridge = CvBridge()
        self.image_sub = rospy.Subscriber("rrbot/camera1/image_raw", Image, self.callback, buff_size=2**26)
        self.image_pub = rospy.Publisher("/annotated_image_plates", Image, queue_size=1)
        self.framenum = 0

    def callback(self,data):
        try:
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")

            rects, threshedFrame = getPlates(cv_image)

            #cv2.drawContours(threshedFrame, [rect.contour for rect in rects], -1, (0,255,0), 2)
            #frame = threshedFrame

            self.framenum += 1
            stackedPlates = None
            if len(rects) != 0:
                rospy.loginfo("Frame " + str(self.framenum))
            for rect in rects:
                rect.perspectiveTransform()
                rospy.loginfo(rect.ocrFrame())
                if stackedPlates is None:
                    stackedPlates = rect.threshedPersFrame_rgb
                else:
                    stackedPlates = np.vstack([stackedPlates, rect.threshedPersFrame_rgb])

            if stackedPlates is None:
                raise NoLicensePlatesException
        
        except NoLicensePlatesException:
            stackedPlates = cv_image
        
        except Exception:
            rospy.logwarn(traceback.format_exc())
            stackedPlates = cv_image
            
        finally:
            self.image_pub.publish(self.bridge.cv2_to_imgmsg(stackedPlates, "bgr8"))
        

def main(args):
    
    rospy.init_node('plate_reader', anonymous=True)
    plate_reader = PlateReader()

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Shutting down")

    cv2.destroyAllWindows()
    
main(sys.argv)