'''Deals with fields'''



import matplotlib as mpl
 #mpl.use('TkAgg')

import matplotlib.pyplot as plt

import numpy as np
from lumopt.utilities.scipy_wrappers import wrapped_GridInterpolator
from lumopt.utilities.scipy_wrappers import trapz3D

eps0=8.854187e-12


class Fields(object):
    '''This object is created from fields loaded from Lumerical field monitors. Several interpolation objects are then created internally to
    enable easy access to the fields in the simulation space

    Use :method:`lumopt.lumerical_methods.lumerical_scripts.get_fields` to load the data properly'''

    def __init__(self,x,y,z,wl,E,D,eps,H):

        def process_input(input):
            if type(input) is float:
                input = np.array([input])
            else:
                input = input.squeeze()
            if input.shape == ():
                input = np.array([input])
            return input

        x,y,z,wl=map(process_input,[x,y,z,wl])

        self.x=x
        self.y=y
        self.z=z
        self.E=E
        self.D=D
        self.H=H
        self.wl=wl
        self.eps=eps
        self.pointing_vect=None
        self.normalized=False

        self.getfield=self.make_field_interpolation_object(self.E)
        if not eps is None:
            self.geteps=self.make_field_interpolation_object(self.eps)
        if not D is None:
            self.getDfield=self.make_field_interpolation_object(self.D)
        if not H is None:
            self.getHfield=self.make_field_interpolation_object(self.H)
        self.evals=0


    def make_field_interpolation_object(self,F):

        Fx_interpolator=wrapped_GridInterpolator((self.x,self.y,self.z,self.wl),F[:,:,:,:,0],method='linear')
        Fy_interpolator=wrapped_GridInterpolator((self.x,self.y,self.z,self.wl),F[:,:,:,:,1],method='linear')
        Fz_interpolator=wrapped_GridInterpolator((self.x,self.y,self.z,self.wl),F[:,:,:,:,2],method='linear')

        def field_interpolator(x,y,z,wl):
            Fx=Fx_interpolator((x,y,z,wl))
            Fy=Fy_interpolator((x,y,z,wl))
            Fz=Fz_interpolator((x,y,z,wl))

            return np.array((Fx,Fy,Fz)).squeeze() #TODO: fix this! This squeeze is a mistery when matlab is used as midman...

        return field_interpolator


    def calculate_pointing_vect(self):
        '''Calculates the Poynting vector and creates an array of it'''
        if self.E is None or self.H is None:
            return ValueError('Either E or H data is missing in the field, cannot calculate Poynting vector')


        pointing_vect=np.zeros(self.E.shape,dtype=np.complex_)

        pointing_vect[:,:,:,:,0]=np.multiply(self.E[:,:,:,:,1],np.conj(self.H[:,:,:,:,2]))-np.multiply(self.E[:,:,:,:,2],np.conj(self.H[:,:,:,:,1]))
        pointing_vect[:,:,:,:,1]=np.multiply(self.E[:,:,:,:,2],np.conj(self.H[:,:,:,:,0]))-np.multiply(self.E[:,:,:,:,0],np.conj(self.H[:,:,:,:,2]))
        pointing_vect[:,:,:,:,2]=np.multiply(self.E[:,:,:,:,0],np.conj(self.H[:,:,:,:,1]))-np.multiply(self.E[:,:,:,:,1],np.conj(self.H[:,:,:,:,0]))

        self.pointing_vect=pointing_vect

        return self.pointing_vect

    def calculate_power(self):
        '''Calculates the Poynting Vector integral of a field for a linear or 2D field monitor, to figure out how much
        power is flowing through the monitor'''

        self.calculate_pointing_vect()
        if len(self.x) == 1:
            normal = [1, 0, 0]
        elif len(self.y) == 1:
            normal = [0, 1, 0]
        elif len(self.z) == 1:  # Test for z last so that 2D simulations make sense
            normal = [0, 0, 1]
        else:
            raise ValueError('Cant normalize power in a volume')

        power = np.zeros(np.shape(self.wl))
        for i, wl in enumerate(self.wl):
            if normal == [1, 0, 0]:
                integrand = self.pointing_vect[:, :, :, i, 0]
            elif normal == [0, 1, 0]:
                integrand = self.pointing_vect[:, :, :, i, 1]
            else:
                integrand = self.pointing_vect[:, :, :, i, 2]
            power[i] = np.real(0.5*trapz3D(integrand, self.x, self.y, self.z))

        return power

    def normalize_to_power(self,power):

        '''Normalizes the fields wrt an input power'''

        for i, wl in enumerate(self.wl):
            self.E[:, :, :, i, :] = self.E[:, :, :, i, :]/np.sqrt(np.abs(power[i]))
            self.H[:, :, :, i, :] = self.H[:, :, :, i, :]/np.sqrt(np.abs(power[i]))
            try:
                self.D[:, :, :, i, :] = self.D[:, :, :, i, :]/np.sqrt(np.abs(power[i]))
            except:
                pass

        self.getfield = self.make_field_interpolation_object(self.E)
        if not self.eps is None:
            self.geteps = self.make_field_interpolation_object(self.eps)
        if not self.D is None:
            self.getDfield = self.make_field_interpolation_object(self.D)
        if not self.H is None:
            self.getHfield = self.make_field_interpolation_object(self.H)

        self.normalized = True

    def normalize_power(self,plot=False):

        '''This is primarily if one wants to do mode overlaps.
        It normalizes the power travelling in the mode through a plane, at every wavelength
        '''
        power=self.calculate_power()
        self.normalize_to_power(power)
        if plot:
            self.plot(H=True)



    def calculate_overlap(self,other_field,remove_E=False,remove_H=False):
        '''Calculates the mode overlap with another field. This assumes this mode has been normalized'''
        if not self.normalized:
            self.normalize_power()
            print 'Normalized the mode being modematched to'

        if not (len(self.x)==len(other_field.x) and len(self.y)==len(other_field.y) and len(self.z)==len(other_field.z) and len(self.wl)==len(other_field.wl)):
            raise ValueError('Fields are not on same grid, (or not the same amount of wavelengths Modematch does not support this (write a method!!)')

        #TODO: MULTIPLE WAVELENGTGHS

        integrand = np.zeros(self.E.shape, dtype=np.complex_)

        # TODO: E x H calculation is terribly ugly, there has got to be a better way

        if remove_H and remove_E:
            raise ValueError('Cant remove_E and remove_H')

        # E x H calculation:
        if remove_E:
            integrand[:, :, :, :, 0] = np.multiply(np.conj(self.E[:, :, :, :, 1]), other_field.H[:, :, :, :, 2]) - np.multiply(
                np.conj(self.E[:, :, :, :, 2]), other_field.H[:, :, :, :, 1])
            integrand[:, :, :, :, 1] = np.multiply(np.conj(self.E[:, :, :, :, 2]), other_field.H[:, :, :, :, 0]) - np.multiply(
                np.conj(self.E[:, :, :, :, 0]), other_field.H[:, :, :, :, 2])
            integrand[:, :, :, :, 2] = np.multiply(np.conj(self.E[:, :, :, :, 0]), other_field.H[:, :, :, :, 1]) - np.multiply(
                np.conj(self.E[:, :, :, :, 1]), other_field.H[:, :, :, :, 0])
            integrand=integrand*2
        elif remove_H:
            integrand[:, :, :, :, 0] = np.multiply(other_field.E[:, :, :, :, 1], np.conj(self.H[:, :, :, :, 2])) - np.multiply(
                other_field.E[:, :, :, :, 2], np.conj(self.H[:, :, :, :, 1]))
            integrand[:, :, :, :, 1] = np.multiply(other_field.E[:, :, :, :, 2], np.conj(self.H[:, :, :, :, 0])) - np.multiply(
                other_field.E[:, :, :, :, 0], np.conj(self.H[:, :, :, :, 2]))
            integrand[:, :, :, :, 2] = np.multiply(other_field.E[:, :, :, :, 0], np.conj(self.H[:, :, :, :, 1])) - np.multiply(
                other_field.E[:, :, :, :, 1], np.conj(self.H[:, :, :, :, 0]))
            integrand = integrand*2
        else:
            integrand[:, :, :, :, 0] = np.multiply(np.conj(self.E[:, :, :, :, 1]), other_field.H[:, :, :, :, 2]) - np.multiply(
                np.conj(self.E[:, :, :, :, 2]), other_field.H[:, :, :, :, 1])+np.multiply(other_field.E[:, :, :, :, 1], np.conj(self.H[:, :, :, :, 2])) - np.multiply(
                other_field.E[:, :, :, :, 2], np.conj(self.H[:, :, :, :, 1]))
            integrand[:, :, :, :, 1] = np.multiply(np.conj(self.E[:, :, :, :, 2]), other_field.H[:, :, :, :, 0]) - np.multiply(
                np.conj(self.E[:, :, :, :, 0]), other_field.H[:, :, :, :, 2])+np.multiply(other_field.E[:, :, :, :, 2], np.conj(self.H[:, :, :, :, 0])) - np.multiply(
                other_field.E[:, :, :, :, 0], np.conj(self.H[:, :, :, :, 2]))
            integrand[:, :, :, :, 2] = np.multiply(np.conj(self.E[:, :, :, :, 0]), other_field.H[:, :, :, :, 1]) - np.multiply(
                np.conj(self.E[:, :, :, :, 1]), other_field.H[:, :, :, :, 0])+np.multiply(other_field.E[:, :, :, :, 0], np.conj(self.H[:, :, :, :, 1])) - np.multiply(
                other_field.E[:, :, :, :, 1], np.conj(self.H[:, :, :, :, 0]))

        if len(self.x) == 1:
            normal = [1, 0, 0]
        elif len(self.y) == 1:
            normal = [0, 1, 0]
        elif len(self.z) == 1:  # Test for z last so that 2D simulations make sense
            normal = [0, 0, 1]

        power = np.zeros(np.shape(self.wl))
        amplitude_prefactors = np.zeros(np.shape(self.wl),dtype=complex)
        #TODO Rename amplitude prefactor to something correct

        for i, wl in enumerate(self.wl):
            if normal == [1, 0, 0]:
                integrand = integrand[:, :, :, i, 0]
            elif normal == [0, 1, 0]:
                integrand = integrand[:, :, :, i, 1]
            else:
                integrand = integrand[:, :, :, i, 2]
            amplitude_prefactor=trapz3D(integrand, self.x, self.y, self.z)
            power[i] = np.abs(amplitude_prefactor)**2/16 # The factor of 16 is different from eq 7.5 of Keraly et al. but with the mode normalization it should be ok
            if remove_E or remove_H: amplitude_prefactor=amplitude_prefactor*2 #not sure why, could have to do with the import H
            amplitude_prefactors[i]=amplitude_prefactor/16 # for the phase of injection in the adjoint sim
        return power,amplitude_prefactors




    def plot(self,ax,title,cmap):
        '''Plots E^2 for the plotter'''
        ax.clear()
        xx, yy = np.meshgrid(self.x, self.y)
        z = (min(self.z) + max(self.z))/2 + 1e-10
        wl=self.wl[0]
        E_fields = [self.getfield(x, y, z, wl) for x, y in zip(xx, yy)]
        Ex = np.array([E[0] for E in E_fields])
        Ey = np.array([E[1] for E in E_fields])
        Ez = np.array([E[2] for E in E_fields])

        ax.pcolormesh(xx*1e6, yy*1e6,np.abs(Ex**2+Ey**2+Ez**2) ,cmap=plt.get_cmap(cmap))
        ax.set_title(title+' $E^2$')
        ax.set_xlabel('x (um)')
        ax.set_ylabel('y (um)')


    def plot_full(self,D=False,E=True,eps=False,H=False,wl=1550e-9,original_grid=True):
        '''Plot the different fields'''

        if E:
            self.plot_field(self.getfield,original_grid=original_grid,wl=wl,name='E')
        if D:
            self.plot_field(self.getDfield, original_grid=original_grid, wl=wl, name='D')
        if eps:
            self.plot_field(self.geteps, original_grid=original_grid, wl=wl, name='eps')
        if H:
            self.plot_field(self.getHfield, original_grid=original_grid, wl=wl, name='H')


    def plot_field(self,field_func=None,original_grid=True,wl=1550e-9,name='field'):
        if field_func is None:
            field_func=self.getfield
        plt.ion()
        if original_grid:
            x = self.x
            y = self.y
        else:
            x = np.linspace(min(self.x), max(self.x), 50)
            y = np.linspace(min(self.y), max(self.y), 50)
        xx, yy = np.meshgrid(x, y)
        z = (min(self.z) + max(self.z))/2+1e-10
        E_fields = [field_func(x, y, z, wl) for x, y in zip(xx, yy)]
        Ex = [E[0] for E in E_fields]
        Ey = [E[1] for E in E_fields]
        Ez = [E[2] for E in E_fields]
        f, (ax1, ax2, ax3) = plt.subplots(1, 3, sharey=True)
        if len(self.x) > 1 and len(self.y) > 1:
            ax1.pcolormesh(xx*1e6, yy*1e6, np.real(Ex), cmap=plt.get_cmap('bwr'))
            ax1.set_title('real('+name+'x)')
            ax2.pcolormesh(xx*1e6, yy*1e6, np.real(Ey), cmap=plt.get_cmap('bwr'))
            ax2.set_title('real('+name+'y)')
            ax3.pcolormesh(xx*1e6, yy*1e6, np.real(Ez), cmap=plt.get_cmap('bwr'))
            ax3.set_title('real('+name+'z)')
            f.canvas.draw()
        elif len(self.x) == 1:
            ax1.plot(yy*1e6, np.real(Ex))
            ax1.set_title('real('+name+'x)')
            ax2.plot(yy*1e6, np.real(Ey))
            ax2.set_title('real('+name+'y)')
            ax3.plot(yy*1e6, np.real(Ez))
            ax3.set_title('real('+name+'z)')
            f.canvas.draw()
        else:
            ax1.plot(xx*1e6, np.real(Ex))
            ax1.set_title('real('+name+'x)')
            ax2.plot(xx*1e6, np.real(Ey))
            ax2.set_title('real('+name+'y)')
            ax3.plot(xx*1e6, np.real(Ez))
            ax3.set_title('real('+name+'z)')
            f.canvas.draw()
        plt.show(block=False)

class FieldsNoInterp(Fields):

    def __init__(self,x,y, z, wl, deltas, E ,D, eps, H):

        def process_input(input):
            if type(input) is float:
                input = np.array([input])
            else:
                input = input.squeeze()
            if input.shape == ():
                input = np.array([input])
            return input

        delta_x=deltas[0]
        delta_y=deltas[1]
        delta_z=deltas[2]

        x, y, z, wl ,delta_x,delta_y,delta_z= map(process_input, [x, y, z, wl,delta_x,delta_y,delta_z])

        deltas=[delta_x,delta_y,delta_z]

        self.x = x
        self.y = y
        self.z = z
        self.deltas=deltas
        self.E = E
        self.D = D
        self.H = H
        self.wl = wl
        self.eps = eps
        self.pointing_vect = None
        self.normalized = False

        self.getfield = self.make_field_interpolation_object_nointerp(self.E)
        if not eps is None:
            self.geteps = self.make_field_interpolation_object_nointerp(self.eps)
        if not D is None:
            self.getDfield = self.make_field_interpolation_object_nointerp(self.D)
        if not H is None:
            self.getHfield = self.make_field_interpolation_object(self.H)
        self.evals = 0

    def make_field_interpolation_object_nointerp(self,F):

        Fx_interpolator = wrapped_GridInterpolator((self.x+self.deltas[0], self.y, self.z, self.wl), F[:, :, :, :, 0], method='linear',bounds_error=False)
        Fy_interpolator = wrapped_GridInterpolator((self.x, self.y+self.deltas[1], self.z, self.wl), F[:, :, :, :, 1], method='linear',bounds_error=False)
        Fz_interpolator = wrapped_GridInterpolator((self.x, self.y, self.z+self.deltas[2], self.wl), F[:, :, :, :, 2], method='linear',bounds_error=False)

        def field_interpolator(x, y, z, wl):
            Fx = Fx_interpolator((x, y, z, wl))
            Fy = Fy_interpolator((x, y, z, wl))
            Fz = Fz_interpolator((x, y, z, wl))

            return np.array(
                (Fx, Fy, Fz)).squeeze()  # TODO: fix this! This squeeze is a mistery when matlab is used as midman...

        return field_interpolator

    def plot(self,ax,title,cmap):
        '''Plots E^2 for the plotter'''
        ax.clear()
        xx, yy = np.meshgrid(self.x[1:-1], self.y[1:-1])
        z = (min(self.z) + max(self.z))/2 + 1e-10
        wl=self.wl[0]
        E_fields = [self.getfield(x, y, z, wl) for x, y in zip(xx, yy)]
        Ex = np.array([E[0] for E in E_fields])
        Ey = np.array([E[1] for E in E_fields])
        Ez = np.array([E[2] for E in E_fields])

        ax.pcolormesh(xx*1e6, yy*1e6,np.abs(Ex**2+Ey**2+Ez**2) ,cmap=plt.get_cmap(cmap))
        ax.set_title(title+' $E^2$')
        ax.set_xlabel('x (um)')
        ax.set_ylabel('y (um)')


if __name__=='__main__':
    from examples.Ysplitter.make_sim import make_sim
    sim=make_sim()
