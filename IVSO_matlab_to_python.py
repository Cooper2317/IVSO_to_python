import numpy as np
from time import time

def IVSO(Xcal, ycal, A_max=10, fold=10, method='autoscaling', num_bms=5000):
    # 初始化设置
    start_time = time()
    m, n = Xcal.shape
    times = 50
    Weight = np.zeros((times, n))
    weight = np.ones(n)
    Ranking = np.zeros((times, n))
    #初始化矩阵
    V_sampling = np.zeros((times, n))
    V_sampling_1 = np.zeros(times, dtype=int)
    RMSECV_min = np.zeros(times)
    var_length = np.zeros(times, dtype=int)
    variables_coef = [None] * times
    # 主循环
    for iter in range(times):
        print(f'开始第 {iter + 1} 次迭代...')

        # 使用 WBMS 生成二进制矩阵以进行采样
        V_binary_matrix = np.zeros((num_bms, n))
        for k in range(n):
            column = np.vstack([np.ones((int(np.round(weight[k] * num_bms)), 1)),
                                np.zeros((num_bms - int(np.round(weight[k] * num_bms)), 1))])
            np.random.shuffle(column)
            column = column.flatten()
            V_binary_matrix[:, k] = column

        # 移除所有元素均为 False 的行（MATLAB 中对应的是全零行）
        all_zeros = np.where(V_binary_matrix.sum(axis=1) != 0)[0]
        V_binary_matrix = V_binary_matrix[all_zeros,:]
        num_bms_2 = V_binary_matrix.shape[0]

        V_sampling[iter, :] = np.sum(V_binary_matrix, axis=0)
        V_sampling_1[iter] = np.sum(V_sampling[iter, :] > 0)  # 记录被选中的变量数量
        nx = V_sampling_1[iter]

        # 计算回归系数
        B = V_binary_matrix.copy()
        for i in range(num_bms_2):
            temp = V_binary_matrix[i, :]
            del_X = (temp == 0)
            V_X_new = Xcal.copy()
            V_X_new = V_X_new[:, ~del_X]

            CV = plscvfold(V_X_new, ycal, A_max, fold, method)
            A_origin = CV['optPC']
            PLS = pls(V_X_new, ycal, A_origin, method)

            selected_indices = np.where(temp==1)[0]
            for j in range(int(np.sum(V_binary_matrix[i,:]))):
                B[i, selected_indices[j]] = abs(PLS['coef_origin'][j, A_origin - 1])

            if np.max(B[i, :]) != 0:
                B[i, :] /= np.max(B[i, :])  # 归一化回归系数

        # 计算变量的重要性指标
        U = np.sum(np.abs(B), axis=0)
        RI = U
        ranking = np.argsort(-RI)  # 根据重要性对变量进行排序

        # 顺序添加变量
        RMSECV = np.zeros((1,nx))
        for j in range(1, nx + 1):
            CV = plscvfold(Xcal[:, ranking[:j]], ycal, A_max, fold, method)
            RMSECV[:, j - 1] = CV['RMSECV']

        va, index = np.min(RMSECV), np.argmin(RMSECV)
        RMSECV_min[iter] = va
        var_length[iter] = index + 1
        variables_coef[iter] = ranking[:index + 1].tolist()
        Ranking[iter, :(index + 1)] = ranking[:(index + 1)]

        # 计算变量的权重
        weight = U / np.max(U) if np.max(U) != 0 else np.zeros_like(U)
        Weight[iter, :] = weight

        elapsed_time = (time() - start_time)/60
        print(f'第 {iter + 1} 次 IVSO 迭代已完成，耗时 {elapsed_time:.2f} min')

        if nx == var_length[iter]:
            break

    non_zero_mask = RMSECV_min != 0
    I = np.argmin(RMSECV_min[non_zero_mask])

    F = {
        'iteration': iter + 1,
        'Sampling_number': V_sampling_1,
        'minRMSECV': RMSECV_min,
        'Select_variables': variables_coef[I],
        'nVar': var_length[I],
        'Rank_variables': Ranking[I, :var_length[I]],
        'Weight': Weight[:iter+1, :],
        'time': (time() - start_time)/60
    }

    print(f'IVSO 的迭代已全部完成，总耗时 {F["time"]:.2f} min')

    return F


def plscvfold(X, y, A=3, K=10, method='center', PROCESS=0, order=0):
    """
    PLS 的 K 折交叉验证 (K-fold Cross-validation for PLS)

    参数:
        X: 样本矩阵，形状为 m x n
        y: 测量属性，形状为 m x 1
        A: 用于交叉验证的最大潜在变量数量
        K: 折数。当 K=m 时，是留一法交叉验证 (leave-one-out CV)
        method: 预处理方法，包括 autoscaling, pareto, minmax, center 或 none.
        PROCESS: =1 : 打印过程。
                 =0 : 不打印过程。
        order: =0 排序，默认值。用于 CV 分区。
               =1 随机。
               =2 原始顺序。
    结果:
        CV：结构化数据 字典
    """
    if order == 0:
        indexyy = np.argsort(y[:,0])
        y = y[indexyy]
        X = X[indexyy, :]
    elif order == 1:
        indexyy = np.random.permutation(len(y))
        X = X[indexyy, :]
        y = y[indexyy]
    elif order == 2:
        indexyy = np.arange(len(y))

    Mx, Nx = X.shape
    A = min([Mx, Nx, A])
    yytest = np.full((Mx, 1), np.nan)
    YR = np.full((Mx, A), np.nan)

    # 初始化分组
    groups = (np.arange(Mx) % K) + 1

    for group in range(1, K + 1):
        testk = np.where(groups == group)[0]
        calk = np.where(groups != group)[0]
        Xcal, ycal = X[calk], y[calk]
        Xtest, ytest = X[testk], y[testk]

        # 数据预处理
        Xs, xpara1, xpara2 = pretreat(Xcal, method)
        ys, ypara1, ypara2 = pretreat(ycal, method)

        # 计算 PLS
        B, W, T, P, Q ,_ ,_ ,_ ,_= pls_nipals(Xs, ys, A) # '_' 占位符

        yp = []
        for j in range(1,A+1):
            Bj = W[:, :j] @ Q[:j]
            C = (ypara2 * Bj) / xpara2.T
            coef = np.vstack([C, ypara1 - xpara1 @ C])

            # 预测
            Xteste = np.hstack([Xtest, np.ones((Xtest.shape[0], 1))])
            ypred = Xteste @ coef
            yp.append(ypred)

        YR[testk, :] = np.column_stack(yp)
        yytest[testk] = ytest

        if PROCESS == 1:
            print(f'第{group}组已完成。')

    # 恢复原始顺序
    YR = YR[np.argsort(indexyy)]
    y = y[np.argsort(indexyy)]

    # 计算误差、PRESS、RMSECV 等指标
    error = YR - np.tile(y, (1, A))
    PRESS = np.sum(error ** 2, axis=0).reshape(1, -1)
    cv = np.sqrt(PRESS / Mx)
    RMSEP, index = np.min(cv), np.argmin(cv)
    SST = np.sum((yytest - np.mean(y)) ** 2)
    SSE = np.sum((YR - y) ** 2, axis=0).reshape(1, -1)
    Q2 = 1 - SSE / SST

    # 输出结果
    CV = {
        'method': method,
        'check': 0,
        'residue': error,
        'RMSECV': RMSEP,
        'Q2_all': Q2.flatten().tolist(),
        'Q2_max': float(Q2[0,index]),
        'Ypred': YR.tolist(),
        'cv': cv.flatten().tolist(),
        'optPC': index + 1  # MATLAB索引从1开始，Python从0开始
    }

    return CV

def pretreat(X, method, para1=None, para2=None):
    """
    数据预处理函数

    参数:
        X: 样本矩阵
        method: 预处理方法，包括 'autoscaling', 'center', 'minmax', 'pareto', 'none'
        para1, para2: 如果提供，则用于逆变换；如果不提供，则计算新的参数。

    返回:
        X: 预处理后的数据
        para1, para2: 计算或提供的预处理参数
    """
    Mx, Nx = X.shape

    if para1 is None and para2 is None:
        # 如果没有提供para1和para2，则根据method计算新的参数
        if method == 'autoscaling':
            para1 = np.mean(X, axis=0).reshape(1, -1)
            para2 = np.std(X, axis=0, ddof=1).reshape(1, -1)  # 使用无偏估计 (ddof=1),matlab计算std默认使用无偏估计，numpy则不是
        elif method == 'center':
            para1 = np.mean(X, axis=0).reshape(1, -1)
            para2 = np.ones((1,Nx))
        elif method == 'minmax':
            para1 = np.min(X, axis=0).reshape(1, -1)
            maxv = np.max(X, axis=0).reshape(1, -1)
            para2 = maxv - para1
        elif method == 'pareto':
            para1 = np.mean(X, axis=0).reshape(1, -1)
            para2 = np.sqrt(np.std(X, axis=0, ddof=1)).reshape(1, -1)
        elif method == 'none':
            para1 = np.zeros((1,Nx))
            para2 = np.ones((1,Nx))
        else:
            raise ValueError('错误的数据预处理方法！')

        # 应用预处理方法
        X = (X - para1) / para2

    elif para1 is not None and para2 is not None:
        X = (X - para1) / para2

    return X, para1, para2


def pls_nipals(X, Y, A):
    """
    使用 NIPALS 算法计算 PLS（偏最小二乘回归）

    参数:
        X: 自变量矩阵 (样本数 x 特征数)
        Y: 因变量矩阵 (样本数 x 1 或更多)
        A: 潜在变量数量

    返回:
        B: 回归系数
        W: 权重矩阵
        T: 得分矩阵
        P: 载荷矩阵
        Q: Y 的载荷向量
        R2X: 解释的 X 方差百分比
        R2Y: 解释的 Y 方差百分比
        X: 剩余 X 矩阵
        Y: 剩余 Y 矩阵
    """
    n, p = X.shape
    Xorig = X.copy()
    Yorig = Y.copy()

    ssqX = np.sum(X ** 2)  # X 的平方和
    ssqY = np.sum(Y ** 2)  # Y 的平方和

    # 初始化输出变量
    W = np.zeros((p, A))
    T = np.zeros((n, A))
    P = np.zeros((p, A))
    Q = np.zeros((A, Y.shape[1]))
    R2X = np.zeros((A,1))
    R2Y = np.zeros((A,1))

    for a in range(A):
        # 初始权重 W
        W[:, a] = X.T @ Y.flatten()
        W[:, a] = W[:, a] / np.linalg.norm(W[:, a])

        # 得分 T
        T[:, a] = X @ W[:, a]

        # 加载 P 和响应加载 Q
        P[:, a] = (X.T @ T[:, a]) / (T[:, a].T @ T[:, a])
        Q[a, :] = (Y.T @ T[:, a]) / (T[:, a].T @ T[:, a])

        # 更新 X 和 Y
        X = X - np.outer(T[:, a], P[:, a])
        Y = Y - T[:, a].reshape(-1, 1) * Q[a, 0]

        # 计算解释方差 R2X 和 R2Y
        R2X[a, 0] = (T[:, a].T @ T[:, a]) * (P[:, a].T @ P[:, a]) / ssqX * 100
        R2Y[a, 0] = (T[:, a].T @ T[:, a]) * (Q[a, 0] ** 2) / ssqY * 100

    # 计算回归系数 B
    W = W @ np.linalg.inv(P.T @ W)
    B = W @ Q

    return B, W, T, P, Q, R2X, R2Y, X, Y


def predict(Xtrain, ytrain, Xtest, ytest, selected_variables, A=10, fold=10, method='center'):
    """
    使用选定变量进行预测

    参数:
        Xtrain: 训练集自变量矩阵
        ytrain: 训练集因变量向量
        Xtest: 测试集自变量矩阵
        ytest: 测试集因变量向量
        selected_variables: 选定的变量索引
        A: 最大潜在变量数量，默认值为10
        fold: K折交叉验证的折数，默认值为10
        method: 数据预处理方法，默认值为中心化 ('center')

    返回:
        RMSEP: 预测均方根误差 (Root Mean Square Error of Prediction)
        RMSEF: 拟合均方根误差 (Root Mean Square Error of Fit)
    """

    # 选择训练集和测试集中的选定变量
    Xtrain = Xtrain[:, selected_variables]
    Xtest = Xtest[:, selected_variables]

    # 使用选定变量进行PLS交叉验证以确定最优潜在变量数量
    CV = plscvfold(Xtrain, ytrain, A, fold, method)
    A_opt = CV['optPC']  # 获取最优潜在变量数量

    # 使用最优潜在变量数量进行PLS建模
    PLS = pls(Xtrain, ytrain, A_opt, method)

    # 扩展测试集数据并进行预测
    Xtest_expand = np.hstack([Xtest, np.ones((Xtest.shape[0], 1))])
    coef = PLS['coef_origin']
    ypred =( Xtest_expand @ coef[:, -1]).reshape(-1,1)  # 使用最后一列系数进行预测

    # 计算RMSEF（拟合均方根误差）和RMSEP（预测均方根误差）
    RMSEF = np.sqrt(PLS['SSE'] / Xtrain.shape[0])
    RMSEP = np.sqrt(np.sum((ytest - ypred) ** 2) / Xtest.shape[0])

    return RMSEP, RMSEF


def pls(X, y, A=2, method='center'):
    """
    偏最小二乘回归 (PLS) 模型计算

    参数:
        X: 自变量矩阵 (样本数 x 特征数)
        y: 因变量向量 (样本数 x 1)
        A: 潜在变量数量，默认值为2
        method: 数据预处理方法，默认值为中心化 ('center')

    返回:
        PLS: 包含模型参数和统计信息的字典
    """

    Mx, Nx = X.shape
    A = min([Mx, Nx, A])  # 确保潜在变量数量不超过样本数和特征数
    check = 0  # 检查数据是否存在问题，1 表示有问题

    # 数据预处理
    Xs, xpara1, xpara2 = pretreat(X, method)
    ys, ypara1, ypara2 = pretreat(y, method)

    if check == 0:
        # 调用 NIPALS 算法进行 PLS 分析
        B, W, T, P, Q, R2X, R2Y, Xr, Yr = pls_nipals(Xs, ys, A)

        # 计算原始尺度下的回归系数
        coef = np.zeros((Nx + 1, A))
        for j in range(A):
            Bj = W[:, :j + 1] @ Q[:j + 1]
            C = (ypara2 * Bj) / xpara2.T
            coef[:, j] = np.vstack([C, np.array(ypara1 - xpara1 @ C)]).flatten()

        # 预测并计算误差
        x_expand = np.hstack([X, np.ones((Mx, 1))])
        ypred = (x_expand @ coef[:, -1]).reshape(-1,1)
        error = ypred - y

        # 计算统计指标
        SST = np.sum((y - np.mean(y)) ** 2)
        SSR = np.sum((ypred - np.mean(y)) ** 2)
        SSE = np.sum((y - ypred) ** 2)
        R2 = 1 - SSE / SST

        # 构建输出结果
        PLS = {
            'method': method,
            'check': 0,
            'coef_origin': coef,
            'coef_standardized': B,
            'X_scores': T,
            'X_loadings': P,
            'R2X': R2X.flatten().tolist(),
            'R2Y': R2Y.flatten().tolist(),
            'Wstar': W,
            'y_est': ypred,
            'residue': error,
            'Xr': Xr,
            'yr': Yr,
            'SST': float(SST),
            'SSR': float(SSR),
            'SSE': float(SSE),
            'RMSEF': float(np.sqrt(SSE / Mx)),
            'R2': float(R2)
        }

    elif check == 1:
        PLS = {
            'method': method,
            'check': 1
        }

    return PLS

from scipy.io import loadmat
mat_data = loadmat(r'D:\Edith\Documents\Program\UAV_MS_Machine_Learning\corn moisture.mat')
Xcal=mat_data['Xcal']
ycal=mat_data['ycal']
Xtest=mat_data['Xtest']
ytest=mat_data['ytest']

F = IVSO(Xcal, ycal, A_max=10, fold=10, method='autoscaling', num_bms=8000)
RMSEP, RMSEF = predict(Xcal, ycal, Xtest, ytest, F['Select_variables'], A=10, fold=10, method='autoscaling')

print(f"RMSEP: {RMSEP}, RMSEF: {RMSEF}")