import os
import numpy as np
np.set_printoptions(precision=4)
np.set_printoptions(suppress=True)
import viso2
import matplotlib.pyplot as plt
from skimage.io import imread
import time
import scipy.io as io
import os.path as osp

def errorMetric(RPred, RGt, TPred, TGt):
    diffRot = (RPred - RGt)
    diffTrans = (TPred - TGt)
    errorRot = np.sqrt(np.sum(np.multiply(diffRot.reshape(-1), diffRot.reshape(-1))))
    errorTrans = np.sqrt(np.sum(np.multiply(diffTrans.reshape(-1), diffTrans.reshape(-1))))

    return errorRot, errorTrans

def runSFM(dataset_path, feature_dir):

    if_vis = True # set to True to do the visualization per frame; the images will be saved at '.vis/'. Turn off if you just want the camera poses and errors
    if_on_screen = True # if True the visualization per frame is going to be displayed realtime on screen; if False there will be no display, but in both options the images will be saved

    # parameter settings (for an example, please download
    # dataset_path = '../dataset'
    img_dir      = os.path.join(dataset_path, 'sequences/00/image_0')
    gt_dir       = os.path.join(dataset_path, 'poses/00.txt')
    calibFile    = os.path.join(dataset_path, 'sequences/00/calib.txt')
    border       = 50;
    gap          = 15;


    # Load the camera calibration information
    with open(calibFile) as fid:
        calibLines = fid.readlines()
        calibLines = [calibLine.strip() for calibLine in calibLines]

    calibInfo = [float(calibStr) for calibStr in calibLines[0].split(' ')[1:]]
    # param = {'f': calibInfo[0], 'cu': calibInfo[2], 'cv': calibInfo[6]}

    # Load the ground-truth depth and rotation
    with open(gt_dir) as fid:
        gtTr = [[float(TrStr) for TrStr in line.strip().split(' ')] for line in fid.readlines()]
    gtTr = np.asarray(gtTr).reshape(-1, 3, 4)

    # param['height'] = 1.6
    # param['pitch']  = -0.08
    # param['match'] = {'pre_step_size': 64}
    first_frame  = 0
    last_frame   = 300

    # init visual odometry
    params = viso2.Mono_parameters()
    params.calib.f = calibInfo[0]
    params.calib.cu = calibInfo[2]
    params.calib.cv = calibInfo[6]
    params.height = 1.6
    params.pitch = -0.08
    params.match.pre_step_size = 64

    # matcher_params = viso2.Matcher_parameters()
    # matcher_params.pre_step_size = 64

    first_frame  = 0
    last_frame   = 300

    # init transformation matrix array
    Tr_total = []
    Tr_total_np = []
    Tr_total.append(viso2.Matrix_eye(4))
    Tr_total_np.append(np.eye(4))

    # init viso module
    visoMono = viso2.VisualOdometryMono(params)

    if if_vis:
        save_path = 'vis_preFeature'
        os.makedirs(save_path, exist_ok=True)

        # create figure
        fig = plt.figure(figsize=(10, 15))
        ax1 = plt.subplot(211)
        ax1.axis('off')
        ax2 = plt.subplot(212)
        ax2.set_xticks(np.arange(-100, 100, step=10))
        ax2.set_yticks(np.arange(-500, 500, step=10))
        ax2.axis('equal')
        ax2.grid()
        if if_on_screen:
            plt.ion()
            plt.show()
        else:
            plt.ioff()

    # for all frames do
    if_replace = False
    errorTransSum = 0
    errorRotSum = 0
    errorRot_list = []
    errorTrans_list =[]

    for frame in range(first_frame, last_frame):
        # 1-based index
        k = frame-first_frame+1

        # read current images
        I = imread(os.path.join(img_dir, '%06d.png'%frame))
        assert(len(I.shape) == 2) # should be grayscale


        if frame > 0:
            flow = np.ascontiguousarray(
                    np.load( osp.join(feature_dir, '%06d_flow.npy' % frame ) ) )

            height, width = I.shape
            u1, v1 = np.meshgrid(np.arange(0, width), np.arange(0, height ) )
            u2 = u1 + flow[:, :, 0]
            v2 = v1 + flow[:, :, 1]

            u1 = u1[border:-border:gap, border:-border:gap ]
            v1 = v1[border:-border:gap, border:-border:gap ]
            u2 = u2[border:-border:gap, border:-border:gap ]
            v2 = v2[border:-border:gap, border:-border:gap ]
            u1 = u1.reshape(-1, 1 )
            v1 = v1.reshape(-1, 1 )
            u2 = u2.reshape(-1, 1 )
            v2 = v2.reshape(-1, 1 )
            preMatches = np.concatenate([u1, v1, u2, v2], axis=1 )
            preMatches = preMatches.astype(np.float32 )
            preMatches = np.ascontiguousarray(preMatches )

            # compute egomotion
            print(preMatches.shape )
            process_result = visoMono.process_frame_preMatch(preMatches )

            Tr = visoMono.getMotion()
            matrixer = viso2.Matrix(Tr)
            Tr_np = np.zeros((4, 4) )
            Tr.toNumpy(Tr_np) # so awkward...
            matches_np = preMatches
        else:
            matches_np = np.zeros((4, 0), dtype = np.float32 )

        # accumulate egomotion, starting with second frame
        if k > 1:
            if process_result is False:
                if_replace = True
                Tr_total.append(Tr_total[-1])
                Tr_total_np.append(Tr_total_np[-1])
            else:
                if_replace = False
                Tr_total.append(Tr_total[-1] * viso2.Matrix_inv(Tr))
                Tr_total_np.append(Tr_total_np[-1] @ np.linalg.inv(Tr_np)) # should be the same
                print(Tr_total_np[-1])

        # output statistics
        num_matches = visoMono.getNumberOfMatches()
        num_inliers = visoMono.getNumberOfInliers()
        #matches = visoMono.getMatches()


        matches_np = matches_np.transpose()
        if if_vis:
            # update image
            ax1.clear()
            ax1.imshow(I, cmap='gray', vmin=0, vmax=255)
            if num_inliers != 0:
                for n in range(num_matches):
                    ax1.plot([matches_np[0, n], matches_np[2, n]], [matches_np[1, n], matches_np[3, n]])
            ax1.set_title('Frame %d'%frame)

            # update trajectory
            if k > 1:
                ax2.plot([Tr_total_np[k-2][0, 3], Tr_total_np[k-1][0, 3]], \
                    [Tr_total_np[k-2][2, 3], Tr_total_np[k-1][2, 3]], 'b.-', linewidth=1)
                ax2.plot([gtTr[k-2][0, 3], gtTr[k-1][0, 3]], \
                    [gtTr[k-2][2, 3], gtTr[k-1][2, 3]], 'r.-', linewidth=1)
            ax2.set_title('Blue: estimated trajectory; Red: ground truth trejectory')

            plt.draw()

        # Compute rotation
        Rpred_p = Tr_total_np[k-2][0:3, 0:3]
        Rpred_c = Tr_total_np[k-1][0:3, 0:3]
        Rpred = Rpred_c.transpose() @ Rpred_p
        Rgt_p = np.squeeze(gtTr[k-2, 0:3, 0:3])
        Rgt_c = np.squeeze(gtTr[k-1, 0:3, 0:3])
        Rgt = Rgt_c.transpose() @ Rgt_p
        # Compute translation
        Tpred_p = Tr_total_np[k-2][0:3, 3:4]
        Tpred_c = Tr_total_np[k-1][0:3, 3:4]
        Tpred = Tpred_c - Tpred_p
        Tgt_p = gtTr[k-2, 0:3, 3:4]
        Tgt_c = gtTr[k-1, 0:3, 3:4]
        Tgt = Tgt_c - Tgt_p
        # Compute errors
        errorRot, errorTrans = errorMetric(Rpred, Rgt, Tpred, Tgt)
        errorRotSum = errorRotSum + errorRot
        errorTransSum = errorTransSum + errorTrans
        # errorRot_list.append(errorRot)
        # errorTrans_list.append(errorTrans)
        print('Mean Error Rotation: %.5f'%(errorRotSum / (k-1)))
        print('Mean Error Translation: %.5f'%(errorTransSum / (k-1)))



        print('== [Result] Frame: %d, Matches %d, Inliers: %.2f'%(frame, num_matches, 100*num_inliers/(num_matches+1e-8)))

        if if_vis:
            # input('Paused; Press Enter to continue') # Option 1: Manually pause and resume
            if if_on_screen:
                plt.pause(0.1) # Or Option 2: enable to this to auto pause for a while after daring to enable animation in case of a delay in drawing
            vis_path = os.path.join(save_path, 'frame%03d.jpg'%frame)
            fig.savefig(vis_path)
            print('Saved at %s'%vis_path)

            if frame % 50 == 0 or frame == last_frame - 1:
                plt.figure(figsize=(10, 15))
                plt.imshow(plt.imread(vis_path))
                plt.axis('off')
                plt.show()


    # input('Press Enter to exit')
