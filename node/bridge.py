#! /usr/bin/env python
from __future__ import print_function
from __future__ import division

import sys
from collections import deque
import traceback
import time
from multiprocessing import Process, Pipe

import roslib
roslib.load_manifest('competition_2019t2')
import rospy
import cv2

from std_msgs.msg import String
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist

from cv_bridge import CvBridge, CvBridgeError

from vanishpt import analyze, NoVanishingPointException
from plates import getPlates, PlateRect
#import pedestrians

TURN_START = 3.1

P_COEFF = -2
I_COEFF = -0.02
D_COEFF = 0
INTEGRAL_LENGTH = 50
MINSPEED = 0.02
MAXSPEED = 0.2
def getSpeedFromError(error):
    if error < 0:
        error *= -1
    return max(MINSPEED, MAXSPEED-error)

class image_converter:

    def __init__(self):
        self.startTime = rospy.get_rostime()
        self.pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        self.image_pub = rospy.Publisher("/annotated_image_vanishing_pt", Image, queue_size=1)
        self.bridge = CvBridge()
        self.image_sub = rospy.Subscriber("rrbot/camera1/image_raw", Image, self.callback)
        self.integral = deque(maxlen=INTEGRAL_LENGTH)
        self.odometer = 0
        self.lengths = 0
        self.heading = 0
        self.lastTickTime = rospy.get_rostime()
        self.frame = None
        self.move = None
        self.localTurnHeading = 0

    def callback(self,data):

        try:
            currentTime = rospy.get_rostime()
            tickDuration = (currentTime - self.lastTickTime).to_sec()
            self.lastTickTime = currentTime
            cv_image = self.bridge.imgmsg_to_cv2(data, "bgr8")
        except CvBridgeError as e:
            print(e)
            return

        self.move = Twist()
        try:
            xFrac, vanishPtFrame = analyze(cv_image)

            rectPairs, threshedFrame = getPlates(cv_image)
            for rectPair in rectPairs:
                for rect in rectPair:
                    rect.labelOnFrame(vanishPtFrame)

            cv2.putText(
                vanishPtFrame, "Pairs:" + str(len(rectPairs)), (20,90), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,0,0), thickness=2
            )

            #cv2.drawContours(vanishPtFrame, [rect.contour for rect in rects], -1, (255,255,0), 2)

            self.frame = vanishPtFrame

            self.integral.append(xFrac)
            intTerm = sum(self.integral)

            # try:
            #     derivTerm = self.integral[-1] - self.integral[-3]
            # except Exception:
            #     derivTerm = 0

            turn_start = 2.5 if self.lengths % 4 == 1 else 2.5
            turn_minimum_radians = -13 if self.lengths % 4 == 1 else -14

            if rospy.get_rostime() - self.startTime < rospy.Duration.from_sec(20):# or pedestrians.hasPedestrian(cv_image):
                self.move.linear.x = 0
                self.move.angular.z = 0

            elif self.lengths % 2 == 1 and self.localTurnHeading > turn_minimum_radians and turn_start < self.odometer < turn_start + 0.25:
                #rospy.loginfo("In turning override")
                self.move.linear.x = 0.01
                self.move.angular.z = -0.5
                self.localTurnHeading += self.move.angular.z * tickDuration

            else:
                self.localTurnHeading = 0
                self.move.linear.x = getSpeedFromError(xFrac)
                self.move.angular.z = xFrac*P_COEFF + intTerm*I_COEFF# + derivTerm * D_COEFF

            self.odometer += self.move.linear.x * tickDuration
            
            # pidStr = "P = %(error).2f, I = %(integral).2f, D = %(deriv).2f" % {"error": xFrac, "integral": intTerm, "deriv": derivTerm}
            # outStr = "v = %(vel).2f, w = %(ang).2f" % {"ang": self.move.angular.z, "vel": self.move.linear.x}
            # cv2.putText(frame, pidStr, (20,20), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,0,0), thickness=1)
        
        except NoVanishingPointException:
            if self.localTurnHeading != 0:
                self.move.linear.x = 0.01
                self.move.angular.z = -0.5
                self.localTurnHeading += self.move.angular.z * tickDuration
            else:
                self.turnCorner()
            self.frame = cv_image

        except Exception:
            rospy.logwarn(traceback.format_exc())
            self.turnCorner()
            self.frame = cv_image
            
        finally:
            self.heading += self.move.angular.z * tickDuration
            #self.heading = self.heading % 17.6
            self.pub.publish(self.move)
            odomStr = "%(length)d: OD %(odom).2f, HD %(head).2f" % {"odom": self.odometer, "head": self.localTurnHeading, "length": self.lengths}
            cv2.putText(
                self.frame, odomStr, (20,50), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,0,0), thickness=2
            )
            self.image_pub.publish(self.bridge.cv2_to_imgmsg(self.frame, "bgr8"))

    def turnCorner(self):
        self.integral.clear()
        self.move.linear.x = 0.06
        self.move.angular.z = -0.35
        #cv2.putText(frame, "No vanishing point", (20,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), thickness=2)
        if self.odometer > 3.5:
            self.odometer = 0
            self.lengths += 1
            rospy.loginfo("Now on length: ")
            rospy.loginfo(self.lengths)
                
        

def main(args):
    
    rospy.init_node('image_converter', anonymous=True)
    ic = image_converter()

    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Shutting down")

    cv2.destroyAllWindows()
    
main(sys.argv)